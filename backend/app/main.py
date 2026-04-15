import os
import uuid
from typing import Optional

import sqlalchemy as sa
from fastapi import FastAPI, Response, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine

from contextlib import asynccontextmanager
from app.db import engine, Base
from app.analytics_engine import AnalyticsEngine
from app.edi_engine import EDIEngine
from app.models_edi import CandidatoEDI
from app.semantic_engine import SemanticIntentEngine
import app.models  # Forzar carga de modelos SQLAlchemy antes de create_all

POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "enterprise_password_2024")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5454")
POSTGRES_DB = os.getenv("POSTGRES_DB", "elecciones_db")

ASYNC_DB_URI = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
async_engine = create_async_engine(ASYNC_DB_URI, pool_pre_ping=True)
semantic_engine = SemanticIntentEngine()
analytics_engine = AnalyticsEngine()

# Mapeo estricto de seguridad para tablas de votos (whitelist anti-inyección).
TABLAS_VOTOS = {
    "PRESIDENCIA": "ine_votos_federal_pres_2024",
    "SENADURIA": "ine_votos_federal_sen_2024",
    "DIPUTACION_FEDERAL": "ine_votos_federal_dip_2024",
    "GUBERNATURA": "ine_votos_local_gub_2024",
    "AYUNTAMIENTO": "ine_votos_local_ayun_2024",
    "DIPUTACION_LOCAL": "ine_votos_local_dip_2024",
    # Alias de compatibilidad para inferencia semántica genérica.
    "DIPUTACION": "ine_votos_federal_dip_2024",
}


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización del entorno (Ejecutado al arranque)
    # create_all enviará el DDL a PostgreSQL si las tablas no existen.
    # Soporta PostGIS y vector automáticamente gracias a los tipos mapeados.
    print("[ENTERPRISE DB] Verificando extensiones PostGIS y pgvector... Sincronizando Modelos.")
    Base.metadata.create_all(bind=engine)
    yield
    # Limpieza o desconexión (Ejecutado al apagado)
    print("[ENTERPRISE DB] Desconectando Pool de DDBB.")

app = FastAPI(
    title="Motor Electoral 2024 - API Espacial",
    description="Backend del Command Center Electoral con soporte GIS, búsqueda vectorial y análisis forense de datos.",
    version="1.0.0",
    lifespan=lifespan
)

# Montar carpeta de medios estáticos
media_dir = os.path.join(os.getcwd(), "media_edi")
os.makedirs(media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")

# Configuración estricta de CORS para el Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Esquema de validación Pydantic
class CandidatoPayload(BaseModel):
    nombre_completo: str
    biografia: str = ""
    telefono: str = ""
    redes_sociales: dict = {}
    foto_perfil_url: str = ""


@app.get("/api/health")
def health_check():
    return {
        "status": "Enterprise System Online",
        "modules": ["PostGIS", "pgvector", "NLP"],
        "version": "1.0.0"
    }


@app.get("/api/v1/mapa/tiles/{cargo}/{z}/{x}/{y}")
async def get_vector_tile_dynamic(
    cargo: str,
    z: int,
    x: int,
    y: int,
    entidad_filter: Optional[int] = None,
    municipio_filter: Optional[int] = None,
    distrito_local_filter: Optional[int] = None,
    distrito_federal_filter: Optional[int] = None,
):
    cargo_key = cargo.upper()
    tabla_destino = TABLAS_VOTOS.get(cargo_key)

    if not tabla_destino:
        return Response(content=b"", media_type="application/x-protobuf")

    where_clauses = []
    params = {"z": z, "x": x, "y": y}

    if entidad_filter:
        where_clauses.append("g.id_entidad = :ent_filter")
        params["ent_filter"] = entidad_filter
    if municipio_filter:
        where_clauses.append(
            "g.seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_municipio = :mun_filter AND id_entidad = g.id_entidad)"
        )
        params["mun_filter"] = municipio_filter
    if distrito_local_filter:
        where_clauses.append(
            "g.seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_distrito_local = :dl_filter AND id_entidad = g.id_entidad)"
        )
        params["dl_filter"] = distrito_local_filter
    if distrito_federal_filter:
        where_clauses.append(
            "g.seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_distrito_federal = :df_filter AND id_entidad = g.id_entidad)"
        )
        params["df_filter"] = distrito_federal_filter

    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = " AND " + where_sql

    async with async_engine.connect() as conn:
        schema_sql = sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        )
        schema_result = await conn.execute(schema_sql, {"table_name": tabla_destino})
        table_columns = {row[0] for row in schema_result.fetchall()}

        id_ent_col = (
            "id_entidad"
            if "id_entidad" in table_columns
            else "ID_ENTIDAD"
            if "ID_ENTIDAD" in table_columns
            else None
        )
        seccion_col = (
            "seccion"
            if "seccion" in table_columns
            else "SECCION"
            if "SECCION" in table_columns
            else None
        )
        if not id_ent_col or not seccion_col:
            return Response(content=b"", media_type="application/x-protobuf")

        votos_col = (
            "votos_desglosados"
            if "votos_desglosados" in table_columns
            else "votos_coaliciones"
            if "votos_coaliciones" in table_columns
            else "VOTOS_DESGLOSADOS"
            if "VOTOS_DESGLOSADOS" in table_columns
            else "VOTOS_COALICIONES"
            if "VOTOS_COALICIONES" in table_columns
            else None
        )
        total_col = (
            "total_votos_calculados"
            if "total_votos_calculados" in table_columns
            else "TOTAL_VOTOS_CALCULADOS"
            if "TOTAL_VOTOS_CALCULADOS" in table_columns
            else None
        )
        mun_col = (
            "id_municipio"
            if "id_municipio" in table_columns
            else "ID_MUNICIPIO"
            if "ID_MUNICIPIO" in table_columns
            else None
        )
        dl_col = (
            "id_distrito_local"
            if "id_distrito_local" in table_columns
            else "ID_DISTRITO_LOCAL"
            if "ID_DISTRITO_LOCAL" in table_columns
            else None
        )
        df_col = (
            "id_distrito_federal"
            if "id_distrito_federal" in table_columns
            else "ID_DISTRITO_FEDERAL"
            if "ID_DISTRITO_FEDERAL" in table_columns
            else None
        )

        id_ent_expr = f"v.{_quote_ident(id_ent_col)}"
        seccion_expr = f"v.{_quote_ident(seccion_col)}"
        id_ent_int_expr = (
            f"NULLIF(regexp_replace({id_ent_expr}::text, '[^0-9-]', '', 'g'), '')::integer"
        )
        seccion_int_expr = (
            f"NULLIF(regexp_replace({seccion_expr}::text, '[^0-9-]', '', 'g'), '')::integer"
        )
        votos_expr = (
            f"COALESCE(v.{_quote_ident(votos_col)}::jsonb, '{{}}'::jsonb)"
            if votos_col
            else "'{}'::jsonb"
        )
        total_expr = (
            f"COALESCE(NULLIF(regexp_replace(v.{_quote_ident(total_col)}::text, '[^0-9.-]', '', 'g'), '')::numeric, 0)"
            if total_col
            else "0"
        )
        mun_expr = (
            f"NULLIF(regexp_replace(v.{_quote_ident(mun_col)}::text, '[^0-9-]', '', 'g'), '')::integer"
            if mun_col
            else "NULL::integer"
        )
        dl_expr = (
            f"NULLIF(regexp_replace(v.{_quote_ident(dl_col)}::text, '[^0-9-]', '', 'g'), '')::integer"
            if dl_col
            else "NULL::integer"
        )
        df_expr = (
            f"NULLIF(regexp_replace(v.{_quote_ident(df_col)}::text, '[^0-9-]', '', 'g'), '')::integer"
            if df_col
            else "NULL::integer"
        )

        geo_context_sql = """
        geo_context AS (
            SELECT id_entidad, seccion, id_municipio, id_distrito_local, id_distrito_federal
            FROM dim_geo_secciones
        ),
        """

        query = sa.text(f"""
            WITH bounds AS (
                SELECT ST_TileEnvelope(:z, :x, :y) AS geom
            ),
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(g.geometry, 3857), bounds.geom) AS geom,
                       g.id_entidad,
                       g.seccion,
                       -- COALESCE garantiza que el frontend reciba un JSON vacío si no hay votos, previniendo crashes
                       COALESCE(v.votos_desglosados, '{{}}'::jsonb) AS votos_desglosados,
                       COALESCE(v.total_votos_calculados, 0) AS total_votos_calculados
                FROM geometria_secciones g
                JOIN bounds ON ST_Intersects(ST_Transform(g.geometry, 3857), bounds.geom)
                -- FIX CRÍTICO: LEFT JOIN asegura que el polígono exista aunque no haya resultados electorales cargados
                LEFT JOIN {tabla_destino} v ON g.id_entidad = v.id_entidad AND g.seccion = v.seccion
                WHERE 1=1 {where_sql}
            )
            SELECT ST_AsMVT(mvtgeom, 'elecciones') AS tile FROM mvtgeom;
        """)

        result = await conn.execute(query, params)
        tile = result.scalar()


    if not tile:
        return Response(content=b"", media_type="application/x-protobuf")
    return Response(content=bytes(tile), media_type="application/x-protobuf")


@app.get("/api/v1/search/intent")
async def search_intent(q: str):
    async with async_engine.connect() as conn:
        intent = await semantic_engine.parse_query(q, conn)
    return intent


@app.get("/api/v1/analitica/ganador")
async def get_ganador_nominal(cargo: str, entidad: int, seccion: int, partido: str):
    async with async_engine.connect() as conn:
        identidad = await analytics_engine.get_winner_identity(
            cargo=cargo,
            entidad=entidad,
            seccion=seccion,
            partido=partido,
            db=conn,
        )
    return identidad


@app.get("/api/v1/mapa/boundaries/{tipo}/{z}/{x}/{y}")
async def get_boundary_tile(
    tipo: str, z: int, x: int, y: int, entidad_filter: Optional[int] = None
):
    # Mapeo de seguridad
    tablas_fronteras = {
        "municipios": "geom_municipios",
        "distritos_locales": "geom_distritos_locales",
        "distritos_federales": "geom_distritos_federales",
    }

    tabla = tablas_fronteras.get(tipo.lower())
    if not tabla:
        return Response(content=b"", media_type="application/x-protobuf")

    where_clause = "WHERE 1=1"
    params = {"z": z, "x": x, "y": y}

    if entidad_filter:
        where_clause += " AND id_entidad = :ent_filter"
        params["ent_filter"] = entidad_filter

    query = sa.text(
        f"""
        WITH bounds AS (
            SELECT ST_TileEnvelope(:z, :x, :y) AS geom
        ),
        mvtgeom AS (
            SELECT ST_AsMVTGeom(ST_Transform(g.geometry, 3857), bounds.geom) AS geom
            FROM {_quote_ident(tabla)} g
            JOIN bounds ON ST_Intersects(ST_Transform(g.geometry, 3857), bounds.geom)
            {where_clause}
        )
        SELECT ST_AsMVT(mvtgeom, 'boundaries') AS tile FROM mvtgeom;
        """
    )

    async with async_engine.connect() as conn:
        result = await conn.execute(query, params)
        tile = result.scalar()

    if not tile:
        return Response(content=b"", media_type="application/x-protobuf")
    return Response(content=bytes(tile), media_type="application/x-protobuf")


# --- APIs DEL EXPEDIENTE DIGITAL DE INTELIGENCIA (EDI) ---
@app.post("/api/v1/edi/upload")
async def upload_candidato_foto(file: UploadFile = File(...)):
    """Recibe la foto, le quita el fondo con IA y la comprime."""
    try:
        contents = await file.read()
        url_imagen = EDIEngine.procesar_imagen_perfil(contents)
        if not url_imagen:
            raise HTTPException(status_code=500, detail="Fallo en el motor de IA al procesar la imagen.")
        return {"status": "success", "url": url_imagen}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/edi/scan_wiki")
async def scan_wikipedia_data(url: str = Form(...)):
    """Minería de datos desde URL externa."""
    data = EDIEngine.escanear_wikipedia(url)
    if not data:
        raise HTTPException(status_code=404, detail="No se pudo extraer información de la URL.")
    return {"status": "success", "data": data}


@app.get("/api/v1/catalogo/municipio")
async def get_nombre_municipio(entidad: int, municipio: int):
    """Resuelve el nombre real del municipio consultando la base de datos (Ingesta Local)."""
    # Intentamos buscar el nombre en la tabla de candidaturas de ayuntamientos que ingerimos previamente
    query = sa.text(
        """
        SELECT actor_politico as nombre_municipio
        FROM ine_candidaturas_local_2024
        WHERE id_entidad = :ent AND id_municipio = :mun AND tipo_candidatura ILIKE '%AYUNTAMIENTO%'
        LIMIT 1
    """
    )
    async with async_engine.connect() as conn:
        result = await conn.execute(query, {"ent": entidad, "mun": municipio})
        row = result.fetchone()
        if row and row[0]:
            return {"nombre": row[0].strip().upper()}
    return {"nombre": f"MUNICIPIO {municipio}"}  # Fallback seguro


@app.get("/api/v1/edi/profile/{candidato_nombre}")
async def get_candidato_profile(candidato_nombre: str):
    """Busca el expediente guardado y genera su trayectoria dinámica."""
    async with async_engine.connect() as conn:
        # 1. Buscar Perfil Editado (EDI)
        query_perfil = sa.text(
            """
            SELECT biografia, telefono, redes_sociales, foto_perfil_url
            FROM edi_candidatos
            WHERE nombre_completo ILIKE :nombre LIMIT 1
        """
        )
        res_perfil = await conn.execute(query_perfil, {"nombre": candidato_nombre})
        row_perfil = res_perfil.fetchone()

        # 2. Generar Trayectoria Dinámica (Buscando en catálogos electorales)
        # Ajustar nombre de tabla según tu BD ('ine_candidaturas_local_2024')
        query_trayectoria = sa.text(
            """
            SELECT '2024' as ciclo, tipo_candidatura as cargo, partido_origen as siglado, 'VICTORIA/PARTICIPACIÓN' as resultado
            FROM ine_candidaturas_local_2024
            WHERE actor_politico ILIKE :nombre OR candidato ILIKE :nombre
            LIMIT 5
        """
        )
        res_tray = await conn.execute(query_trayectoria, {"nombre": f"%{candidato_nombre}%"})
        trayectorias = [
            {"ciclo": t[0], "cargo": t[1], "siglado": t[2], "resultado": t[3]}
            for t in res_tray.fetchall()
        ]

    # Preparamos la respuesta garantizando que la estructura no falle en el frontend
    response_data = {
        "biografia": row_perfil[0] if row_perfil else "",
        "telefono": row_perfil[1] if row_perfil else "",
        "redes_sociales": row_perfil[2] if row_perfil else {},
        "foto_perfil_url": row_perfil[3] if row_perfil else "",
        "trayectoria": trayectorias,
    }

    return {"status": "success", "data": response_data}


@app.post("/api/v1/edi/profile")
async def save_candidato_profile(payload: CandidatoPayload):
    """Guarda o actualiza el expediente del candidato."""
    # Referencia explícita del modelo para asegurar carga/import del esquema EDI.
    _ = CandidatoEDI
    async with async_engine.begin() as conn:
        # Verificar si existe
        check_query = sa.text("SELECT id FROM edi_candidatos WHERE nombre_completo = :nombre")
        result = await conn.execute(check_query, {"nombre": payload.nombre_completo})
        row = result.fetchone()

        import json
        redes_json = json.dumps(payload.redes_sociales)

        if row:
            # Update
            update_query = sa.text(
                """
                UPDATE edi_candidatos
                SET biografia = :bio, telefono = :tel, redes_sociales = :redes::jsonb, foto_perfil_url = :foto
                WHERE nombre_completo = :nombre
            """
            )
            await conn.execute(
                update_query,
                {
                    "bio": payload.biografia,
                    "tel": payload.telefono,
                    "redes": redes_json,
                    "foto": payload.foto_perfil_url,
                    "nombre": payload.nombre_completo,
                },
            )
        else:
            # Insert
            insert_query = sa.text(
                """
                INSERT INTO edi_candidatos (id, nombre_completo, biografia, telefono, redes_sociales, foto_perfil_url)
                VALUES (:id, :nombre, :bio, :tel, :redes::jsonb, :foto)
            """
            )
            await conn.execute(
                insert_query,
                {
                    "id": uuid.uuid4().hex,
                    "nombre": payload.nombre_completo,
                    "bio": payload.biografia,
                    "tel": payload.telefono,
                    "redes": redes_json,
                    "foto": payload.foto_perfil_url,
                },
            )

    return {"status": "success", "message": "Expediente guardado correctamente"}
