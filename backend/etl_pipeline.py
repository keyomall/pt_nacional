"""
Pipeline ETL modular para ingesta electoral 2024.

Este módulo define componentes reutilizables para:
1) Ingesta tabular de datos INE vía pandas + SQLAlchemy.
2) Ingesta espacial MAGAR vía GeoPandas + PostGIS (GeoAlchemy2).

Nota: El módulo solo define lógica y utilidades. No ejecuta carga automática al importarse.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence, Set, Tuple

import geopandas as gpd
import pandas as pd
from geoalchemy2 import Geometry
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB


DEFAULT_DB_URL = "postgresql://admin:enterprise_password_2024@127.0.0.1:5454/elecciones_db"
DEFAULT_CHUNK_SIZE = 10_000
TARGET_CRS = "EPSG:4326"

# Valores nulos comunes en datasets de cómputos electorales.
NULL_SENTINELS: Tuple[str, ...] = ("-", "N/A", "NA", "n/a", "na", "")


logger = logging.getLogger("etl_pipeline")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s | %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class ETLPipelineError(Exception):
    """Excepción base de la capa ETL."""


class DatabaseConnector:
    """Gestiona Engine y sesiones SQLAlchemy para operaciones ETL."""

    def __init__(
        self,
        db_url: str = DEFAULT_DB_URL,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ) -> None:
        self.db_url = db_url
        self.engine: Engine = create_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            future=True,
        )
        self._session_factory = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        logger.info("Conector SQLAlchemy inicializado para %s", db_url)

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Entrega una sesión transaccional con commit/rollback seguro."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Fallo transaccional. Rollback aplicado.")
            raise ETLPipelineError("Error en transacción de base de datos.") from exc
        finally:
            session.close()

    def test_connection(self) -> None:
        """Valida conectividad básica contra PostgreSQL."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Conexión a base de datos validada.")
        except SQLAlchemyError as exc:
            logger.exception("No fue posible validar la conexión a PostgreSQL.")
            raise ETLPipelineError("Conexión inválida con PostgreSQL.") from exc

    def dispose(self) -> None:
        """Libera recursos del pool."""
        self.engine.dispose()
        logger.info("Pool SQLAlchemy liberado.")


class INEDataProcessor:
    """Procesador ETL para archivos CSV del INE con enfoque de memoria acotada."""

    def __init__(self, db: DatabaseConnector, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self.db = db
        self.chunk_size = chunk_size

    @staticmethod
    def _normalize_nulls(df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.replace({value: None for value in NULL_SENTINELS})
        normalized = normalized.where(pd.notna(normalized), None)
        return normalized

    @staticmethod
    def _infer_vote_columns(
        df: pd.DataFrame,
        metadata_columns: Optional[Sequence[str]] = None,
    ) -> List[str]:
        metadata_set: Set[str] = {col.lower().strip() for col in (metadata_columns or [])}
        excluded_tokens = {"total", "lista_nominal", "participacion", "casillas", "id", "seccion", "distrito"}
        vote_columns: List[str] = []

        for column in df.columns:
            normalized = column.lower().strip()
            if normalized in metadata_set:
                continue
            if any(token in normalized for token in excluded_tokens):
                continue

            series = pd.to_numeric(df[column], errors="coerce")
            ratio_numeric = float(series.notna().mean()) if len(series) else 0.0
            if ratio_numeric >= 0.5:
                vote_columns.append(column)

        return vote_columns

    @staticmethod
    def _build_votes_payload(df: pd.DataFrame, vote_columns: Sequence[str]) -> List[Dict[str, Optional[float]]]:
        if not vote_columns:
            return [{} for _ in range(len(df))]

        votes_df = df.loc[:, vote_columns].copy()
        for column in vote_columns:
            votes_df[column] = pd.to_numeric(votes_df[column], errors="coerce")

        votes_df = votes_df.where(pd.notna(votes_df), None)
        payload = votes_df.to_dict(orient="records")
        return payload

    def read_csv_in_chunks(
        self,
        csv_path: str | Path,
        skiprows: int = 7,
        sep: str = ",",
        encoding: str = "latin-1",
    ) -> Iterable[pd.DataFrame]:
        """
        Lee CSV del INE en bloques para minimizar consumo de RAM.
        """
        source = Path(csv_path)
        if not source.exists():
            raise ETLPipelineError(f"Archivo CSV no encontrado: {source}")

        logger.info("Iniciando lectura chunked de %s", source)
        try:
            yield from pd.read_csv(
                source,
                skiprows=skiprows,
                sep=sep,
                chunksize=self.chunk_size,
                dtype=str,
                encoding=encoding,
                keep_default_na=True,
                na_values=list(NULL_SENTINELS),
                low_memory=False,
            )
        except Exception as exc:
            logger.exception("Error al leer CSV INE: %s", source)
            raise ETLPipelineError("Fallo durante lectura CSV por chunks.") from exc

    def transform_chunk(
        self,
        chunk: pd.DataFrame,
        metadata_columns: Optional[Sequence[str]] = None,
        payload_column: str = "votos_coaliciones",
        drop_vote_columns: bool = False,
    ) -> pd.DataFrame:
        transformed = self._normalize_nulls(chunk.copy())
        vote_columns = self._infer_vote_columns(transformed, metadata_columns=metadata_columns)
        transformed[payload_column] = self._build_votes_payload(transformed, vote_columns)

        if drop_vote_columns and vote_columns:
            transformed = transformed.drop(columns=vote_columns, errors="ignore")

        logger.info(
            "Chunk transformado. Registros=%s | Columnas voto detectadas=%s",
            len(transformed),
            len(vote_columns),
        )
        return transformed

    def process_csv_chunks(
        self,
        csv_path: str | Path,
        skiprows: int = 7,
        sep: str = ",",
        encoding: str = "latin-1",
        metadata_columns: Optional[Sequence[str]] = None,
        payload_column: str = "votos_coaliciones",
        drop_vote_columns: bool = False,
    ) -> Generator[pd.DataFrame, None, None]:
        for chunk_number, chunk in enumerate(
            self.read_csv_in_chunks(csv_path, skiprows=skiprows, sep=sep, encoding=encoding),
            start=1,
        ):
            transformed = self.transform_chunk(
                chunk=chunk,
                metadata_columns=metadata_columns,
                payload_column=payload_column,
                drop_vote_columns=drop_vote_columns,
            )
            logger.info("[INFO] Chunk procesado #%s | filas=%s", chunk_number, len(transformed))
            yield transformed

    def load_csv_to_postgres(
        self,
        csv_path: str | Path,
        target_table: str,
        schema: str = "public",
        if_exists: str = "append",
        skiprows: int = 7,
        sep: str = ",",
        encoding: str = "latin-1",
        metadata_columns: Optional[Sequence[str]] = None,
        payload_column: str = "votos_coaliciones",
        drop_vote_columns: bool = False,
    ) -> int:
        """
        Carga un CSV INE hacia PostgreSQL por lotes.
        Retorna el total de registros enviados.
        """
        inserted_rows = 0
        first_chunk = True

        for transformed_chunk in self.process_csv_chunks(
            csv_path=csv_path,
            skiprows=skiprows,
            sep=sep,
            encoding=encoding,
            metadata_columns=metadata_columns,
            payload_column=payload_column,
            drop_vote_columns=drop_vote_columns,
        ):
            write_mode = if_exists if first_chunk else "append"
            transformed_chunk.to_sql(
                name=target_table,
                con=self.db.engine,
                schema=schema,
                if_exists=write_mode,
                index=False,
                method="multi",
                chunksize=self.chunk_size,
                dtype={payload_column: JSONB},
            )
            inserted_rows += len(transformed_chunk)
            first_chunk = False
            logger.info(
                "[INFO] Chunk cargado a PostgreSQL | tabla=%s.%s | acumulado=%s",
                schema,
                target_table,
                inserted_rows,
            )

        if inserted_rows == 0:
            logger.warning("No se insertaron filas para %s", csv_path)
        else:
            logger.info("Carga finalizada. Total filas insertadas: %s", inserted_rows)
        return inserted_rows


class MagarSpatialProcessor:
    """Procesador de geometrías MAGAR con estándar CRS web y volcado PostGIS."""

    def __init__(self, db: DatabaseConnector, target_crs: str = TARGET_CRS) -> None:
        self.db = db
        self.target_crs = target_crs

    @staticmethod
    def _infer_postgis_geometry_type(gdf: gpd.GeoDataFrame) -> str:
        geom_types = {str(geom_type).upper() for geom_type in gdf.geometry.geom_type.dropna().unique()}
        if not geom_types:
            return "GEOMETRY"
        if geom_types == {"POINT"}:
            return "POINT"
        if geom_types == {"LINESTRING"}:
            return "LINESTRING"
        if geom_types.issubset({"POLYGON", "MULTIPOLYGON"}):
            return "MULTIPOLYGON"
        return "GEOMETRY"

    def read_shapefile(self, shapefile_path: str | Path) -> gpd.GeoDataFrame:
        source = Path(shapefile_path)
        if not source.exists():
            raise ETLPipelineError(f"Shapefile no encontrado: {source}")

        try:
            gdf = gpd.read_file(source)
            if gdf.empty:
                raise ETLPipelineError(f"Shapefile vacío: {source}")
            logger.info("Shapefile leído correctamente: %s (filas=%s)", source, len(gdf))
            return gdf
        except Exception as exc:
            logger.exception("No fue posible leer shapefile: %s", source)
            raise ETLPipelineError("Fallo al leer shapefile MAGAR.") from exc

    def enforce_wgs84(self, gdf: gpd.GeoDataFrame, source_crs: Optional[str] = None) -> gpd.GeoDataFrame:
        if gdf.crs is None:
            if not source_crs:
                raise ETLPipelineError(
                    "GeoDataFrame sin CRS. Debe indicar source_crs para reproyectar de forma segura."
                )
            gdf = gdf.set_crs(source_crs)
            logger.info("CRS de origen asignado manualmente: %s", source_crs)

        if str(gdf.crs) != self.target_crs:
            gdf = gdf.to_crs(self.target_crs)
            logger.info("CRS reproyectado a %s", self.target_crs)
        else:
            logger.info("CRS ya compatible con web (%s).", self.target_crs)

        gdf = gdf[gdf.geometry.notnull()].copy()
        gdf = gdf[~gdf.geometry.is_empty].copy()
        return gdf

    def load_geodataframe_to_postgis(
        self,
        gdf: gpd.GeoDataFrame,
        target_table: str,
        schema: str = "public",
        if_exists: str = "append",
        source_crs: Optional[str] = None,
    ) -> int:
        if gdf.empty:
            raise ETLPipelineError("GeoDataFrame vacío. No hay datos para cargar.")

        prepared = self.enforce_wgs84(gdf, source_crs=source_crs)
        geometry_col = prepared.geometry.name
        geom_type = self._infer_postgis_geometry_type(prepared)

        try:
            prepared.to_postgis(
                name=target_table,
                con=self.db.engine,
                schema=schema,
                if_exists=if_exists,
                index=False,
                chunksize=5_000,
                dtype={geometry_col: Geometry(geom_type, srid=4326)},
            )
            logger.info(
                "[INFO] Carga espacial completada | tabla=%s.%s | registros=%s | tipo_geom=%s",
                schema,
                target_table,
                len(prepared),
                geom_type,
            )
            return len(prepared)
        except Exception as exc:
            logger.exception("Fallo al volcar GeoDataFrame a PostGIS.")
            raise ETLPipelineError("Error durante carga espacial en PostGIS.") from exc

    def load_shapefile_to_postgis(
        self,
        shapefile_path: str | Path,
        target_table: str,
        schema: str = "public",
        if_exists: str = "append",
        source_crs: Optional[str] = None,
    ) -> int:
        gdf = self.read_shapefile(shapefile_path)
        return self.load_geodataframe_to_postgis(
            gdf=gdf,
            target_table=target_table,
            schema=schema,
            if_exists=if_exists,
            source_crs=source_crs,
        )


def build_default_components(
    db_url: str = DEFAULT_DB_URL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Tuple[DatabaseConnector, INEDataProcessor, MagarSpatialProcessor]:
    """
    Factory de conveniencia para construir los tres componentes principales.
    """
    connector = DatabaseConnector(db_url=db_url)
    ine_processor = INEDataProcessor(db=connector, chunk_size=chunk_size)
    magar_processor = MagarSpatialProcessor(db=connector, target_crs=TARGET_CRS)
    return connector, ine_processor, magar_processor


if __name__ == "__main__":
    logger.info(
        "Módulo ETL cargado correctamente. "
        "No se ejecuta ingesta automática; utilice las clases para cargas controladas."
    )
