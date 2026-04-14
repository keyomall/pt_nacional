import os
import sqlalchemy as sa
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine

from contextlib import asynccontextmanager
from app.db import engine, Base
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización del entorno (Ejecutado al arranque)
    # create_all enviará el DDL a PostgreSQL si las tablas no existen.
    # Soporta PostGIS y vector automáticamente gracias a los tipos mapeados.
    print("🚀 [ENTERPRISE DB] Verificando extensiones PostGIS y pgvector... Sincronizando Modelos.")
    Base.metadata.create_all(bind=engine)
    yield
    # Limpieza o desconexión (Ejecutado al apagado)
    print("🛑 [ENTERPRISE DB] Desconectando Pool de DDBB.")

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


@app.get("/api/v1/mapa/tiles/presidencia/{z}/{x}/{y}")
async def get_vector_tile(z: int, x: int, y: int):
    """
    Motor de Vector Tiles (MVT).
    Cruza geometria seccional de Magar con resultados INE.
    """
    query = sa.text(
        """
        WITH bounds AS (
            SELECT ST_TileEnvelope(:z, :x, :y) AS geom
        ),
        mvtgeom AS (
            SELECT
                ST_AsMVTGeom(ST_Transform(g.geometry, 3857), bounds.geom) AS geom,
                g.id_entidad,
                g.seccion,
                jsonb_build_object(
                    'MORENA', COALESCE(NULLIF(regexp_replace(v."MORENA"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'PAN', COALESCE(NULLIF(regexp_replace(v."PAN"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'PRI', COALESCE(NULLIF(regexp_replace(v."PRI"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'MC', COALESCE(NULLIF(regexp_replace(v."MC"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'PT', COALESCE(NULLIF(regexp_replace(v."PT"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'PVEM', COALESCE(NULLIF(regexp_replace(v."PVEM"::text, '[^0-9-]', '', 'g'), '')::integer, 0),
                    'PRD', COALESCE(NULLIF(regexp_replace(v."PRD"::text, '[^0-9-]', '', 'g'), '')::integer, 0)
                ) AS votos_desglosados,
                COALESCE(NULLIF(regexp_replace(v."TOTAL_VOTOS_CALCULADOS"::text, '[^0-9-]', '', 'g'), '')::integer, 0)
                    AS total_votos_calculados
            FROM geometria_secciones g
            JOIN ine_votos_federal_pres_2024_test v
              ON g.id_entidad = v."ID_ENTIDAD" AND g.seccion = v."SECCION"
            JOIN bounds
              ON ST_Intersects(ST_Transform(g.geometry, 3857), bounds.geom)
        )
        SELECT ST_AsMVT(mvtgeom, 'elecciones') AS tile FROM mvtgeom;
        """
    )

    async with async_engine.connect() as conn:
        result = await conn.execute(query, {"z": z, "x": x, "y": y})
        tile = result.scalar()

    if not tile:
        return Response(content=b"", media_type="application/x-protobuf")
    return Response(content=bytes(tile), media_type="application/x-protobuf")
