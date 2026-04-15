import os
from typing import Optional

import sqlalchemy as sa
from fastapi import FastAPI, Response, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine

from contextlib import asynccontextmanager
from app.db import engine, Base
from app.analytics_engine import AnalyticsEngine
from app.edi_engine import EDIEngine
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
        where_clauses.append("c.id_municipio = :mun_filter")
        params["mun_filter"] = municipio_filter
    if distrito_local_filter:
        where_clauses.append("c.id_distrito_local = :dl_filter")
        params["dl_filter"] = distrito_local_filter
    if distrito_federal_filter:
        where_clauses.append("c.id_distrito_federal = :df_filter")
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

        query = sa.text(
            f"""
            WITH bounds AS (
                SELECT ST_TileEnvelope(:z, :x, :y) AS geom
            ),
            {geo_context_sql}
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(g.geometry, 3857), bounds.geom) AS geom,
                       g.id_entidad,
                       g.seccion,
                       c.id_municipio,
                       c.id_distrito_local,
                       c.id_distrito_federal,
                       {votos_expr} AS votos_desglosados,
                       {total_expr} AS total_votos_calculados
                FROM geometria_secciones g
                JOIN bounds
                  ON ST_Intersects(ST_Transform(g.geometry, 3857), bounds.geom)
                LEFT JOIN geo_context c
                  ON g.id_entidad::integer = c.id_entidad::integer
                 AND g.seccion::integer = c.seccion::integer
                LEFT JOIN {_quote_ident(tabla_destino)} v
                  ON g.id_entidad::integer = {id_ent_int_expr}
                 AND g.seccion::integer = {seccion_int_expr}
                WHERE 1=1 {where_sql}
            )
            SELECT ST_AsMVT(mvtgeom, 'elecciones') AS tile FROM mvtgeom;
            """
        )

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
