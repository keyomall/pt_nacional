import os
from typing import Optional

import sqlalchemy as sa
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from contextlib import asynccontextmanager
from app.db import engine, Base
from app.analytics_engine import AnalyticsEngine
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
    cargo: str, z: int, x: int, y: int, entidad_filter: Optional[int] = None
):
    """
    Motor MVT Dinámico.
    Selecciona la tabla de resultados según el cargo solicitado.
    """
    cargo_key = cargo.upper()
    tabla_destino = TABLAS_VOTOS.get(cargo_key)
    if not tabla_destino:
        return Response(content=b"", media_type="application/x-protobuf")

    where_clause = ""
    params: dict[str, int] = {"z": z, "x": x, "y": y}
    if entidad_filter is not None:
        where_clause = "AND g.id_entidad = :ent_filter"
        params["ent_filter"] = entidad_filter

    schema_sql = sa.text(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
        """
    )
    async with async_engine.connect() as conn:
        schema_result = await conn.execute(schema_sql, {"table_name": tabla_destino})
        table_columns = {row[0] for row in schema_result.fetchall()}

        id_ent_col = "id_entidad" if "id_entidad" in table_columns else "ID_ENTIDAD" if "ID_ENTIDAD" in table_columns else None
        seccion_col = "seccion" if "seccion" in table_columns else "SECCION" if "SECCION" in table_columns else None
        total_col = (
            "total_votos_calculados"
            if "total_votos_calculados" in table_columns
            else "TOTAL_VOTOS_CALCULADOS"
            if "TOTAL_VOTOS_CALCULADOS" in table_columns
            else None
        )
        votos_json_col = (
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

        if not id_ent_col or not seccion_col:
            return Response(content=b"", media_type="application/x-protobuf")

        id_ent_expr = f"v.{_quote_ident(id_ent_col)}"
        seccion_expr = f"v.{_quote_ident(seccion_col)}"
        if votos_json_col:
            votos_expr = f"COALESCE(v.{_quote_ident(votos_json_col)}::jsonb, '{{}}'::jsonb)"
        else:
            excluded = {"id_entidad", "ID_ENTIDAD", "seccion", "SECCION", "total_votos_calculados", "TOTAL_VOTOS_CALCULADOS"}
            excluded_ops = "".join(f" - '{col}'" for col in sorted(table_columns.intersection(excluded)))
            votos_expr = f"(to_jsonb(v){excluded_ops})"

        if total_col:
            total_expr = (
                f"COALESCE(NULLIF(regexp_replace(v.{_quote_ident(total_col)}::text, '[^0-9-]', '', 'g'), '')::integer, 0)"
            )
        else:
            total_expr = "0"

        query = sa.text(
            f"""
            WITH bounds AS (
                SELECT ST_TileEnvelope(:z, :x, :y) AS geom
            ),
            geo_context AS (
                -- Extraemos el linaje geográfico único por sección
                SELECT DISTINCT id_entidad, seccion, id_municipio, id_distrito_local, id_distrito_federal
                FROM eleccion_2024_casillas
            ),
            mvtgeom AS (
                SELECT
                    ST_AsMVTGeom(ST_Transform(g.geometry, 3857), bounds.geom) AS geom,
                    g.id_entidad,
                    g.seccion,
                    c.id_municipio,
                    c.id_distrito_local,
                    c.id_distrito_federal,
                    COALESCE(({votos_expr}), '{{}}'::jsonb) AS votos_desglosados,
                    COALESCE(({total_expr}), 0) AS total_votos_calculados
                FROM geometria_secciones g
                LEFT JOIN geo_context c
                  ON g.id_entidad = c.id_entidad AND g.seccion = c.seccion
                LEFT JOIN {_quote_ident(tabla_destino)} v
                  ON g.id_entidad = {id_ent_expr} AND g.seccion = {seccion_expr}
                JOIN bounds
                  ON ST_Intersects(ST_Transform(g.geometry, 3857), bounds.geom)
                WHERE 1=1 {where_clause}
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
