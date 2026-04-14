"""
Batch manager para ingesta masiva electoral 2024 con control delta.

Características:
1) Crawling recursivo de CSVs.
2) Ruteo estricto para evitar duplicidad por agregaciones (_MUN, _SEC, etc.).
3) Checkpointing por archivo/chunk en PostgreSQL.
4) Reporte delta final para auditoría operativa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB

from etl_pipeline import (
    DEFAULT_DB_URL,
    DatabaseConnector,
    INEDataProcessor,
    build_default_components,
    logger,
)


CHECKPOINT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS etl_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL,
    rows_inserted INT DEFAULT 0,
    errors_encountered INT DEFAULT 0,
    last_processed_chunk INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);
"""


@dataclass(frozen=True)
class RouteDecision:
    target_table: Optional[str]
    sep: str = ","
    skiprows: int = 0
    reason: Optional[str] = None

    @property
    def should_skip(self) -> bool:
        return self.target_table is None


@dataclass
class DeltaReport:
    csv_found: int = 0
    ignored: int = 0
    skipped_delta: int = 0
    processed_today: int = 0
    inserted_rows_today: int = 0
    failures: int = 0

    def render(self) -> str:
        return "\n".join(
            [
                "=========================================",
                "REPORTE DELTA DE INGESTA MASIVA",
                "=========================================",
                f"Archivos CSV Encontrados: {self.csv_found}",
                f"Archivos Ignorados (Redundancia/No-Casilla): {self.ignored}",
                f"Archivos Saltados (Ya procesados BD): {self.skipped_delta}",
                f"Archivos Procesados Hoy: {self.processed_today}",
                f"Total Filas Insertadas Hoy: {self.inserted_rows_today}",
                f"Errores/Fallos: {self.failures}",
                "=========================================",
            ]
        )


class BatchIngestionManager:
    """Orquesta ingesta masiva con ruteo de negocio + checkpoint delta."""

    _REJECT_SUFFIXES = (
        "_MUN.CSV",
        "_SEC.CSV",
        "_DIS.CSV",
        "_MUNCAND.CSV",
        "_PP.CSV",
    )
    _FEDERAL_CANDIDATURAS_TABLES = {
        "ine_candidaturas_federal_pres_2024",
        "ine_candidaturas_federal_sen_2024",
        "ine_candidaturas_federal_dip_2024",
    }

    def __init__(self, db: DatabaseConnector, processor: INEDataProcessor) -> None:
        self.db = db
        self.processor = processor

    def ensure_checkpoint_table(self) -> None:
        with self.db.engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            connection.execute(text(CHECKPOINT_TABLE_DDL))
        logger.info("[INFO] Tabla administrativa etl_execution_logs verificada.")

    @staticmethod
    def route_csv(file_path: Path) -> RouteDecision:
        absolute = str(file_path.resolve(strict=False))
        normalized_path = absolute.upper()
        file_name = file_path.name.upper()

        if "PARTICIPANTES" in normalized_path:
            return RouteDecision(target_table=None, reason="Contiene PARTICIPANTES")
        if file_name.endswith(BatchIngestionManager._REJECT_SUFFIXES):
            return RouteDecision(target_table=None, reason="Agregación redundante")

        # FEDERALES
        if "PRES_CANDIDATURAS" in file_name and file_name.endswith(".CSV"):
            return RouteDecision(target_table="ine_candidaturas_federal_pres_2024", sep="|", skiprows=0)
        if "SEN_CANDIDATURAS" in file_name and file_name.endswith(".CSV"):
            return RouteDecision(target_table="ine_candidaturas_federal_sen_2024", sep="|", skiprows=0)
        if "DIP_FED_CANDIDATURAS" in file_name and file_name.endswith(".CSV"):
            return RouteDecision(target_table="ine_candidaturas_federal_dip_2024", sep="|", skiprows=0)
        if file_name.endswith("PRES_2024.CSV"):
            return RouteDecision(target_table="ine_votos_federal_pres_2024", sep="|", skiprows=7)
        if file_name.endswith("SEN_2024.CSV"):
            return RouteDecision(target_table="ine_votos_federal_sen_2024", sep="|", skiprows=7)
        if file_name.endswith("DIP_FED_2024.CSV"):
            return RouteDecision(target_table="ine_votos_federal_dip_2024", sep="|", skiprows=7)

        # LOCALES (solo casilla)
        if "AYUNTAMIENTOS" in normalized_path and file_name.endswith("_CAS.CSV"):
            return RouteDecision(target_table="ine_votos_local_ayun_2024", sep=",", skiprows=0)
        if "DIPUTACIONES LOC" in normalized_path and file_name.endswith("_CAS.CSV"):
            return RouteDecision(target_table="ine_votos_local_dip_2024", sep=",", skiprows=0)
        if "GUBERNATURA" in normalized_path and file_name.endswith("_CAS.CSV"):
            return RouteDecision(target_table="ine_votos_local_gub_2024", sep=",", skiprows=0)

        # CANDIDATURAS (catálogos)
        if file_name.startswith("INTEGRACION_") and file_name.endswith(".CSV"):
            return RouteDecision(target_table="ine_candidaturas_local_2024", sep=",", skiprows=0)

        return RouteDecision(target_table=None, reason="Sin regla de ruteo válida")

    def _get_checkpoint(self, file_path: str) -> Optional[Dict[str, int | str]]:
        query = text(
            """
            SELECT status, rows_inserted, errors_encountered, last_processed_chunk
            FROM etl_execution_logs
            WHERE file_path = :file_path
            """
        )
        with self.db.engine.connect() as connection:
            row = connection.execute(query, {"file_path": file_path}).mappings().first()
        return dict(row) if row else None

    def _upsert_checkpoint(
        self,
        file_path: str,
        status: str,
        rows_inserted: int,
        errors_encountered: int,
        last_processed_chunk: int,
    ) -> None:
        statement = text(
            """
            INSERT INTO etl_execution_logs (
                file_path, status, rows_inserted, errors_encountered, last_processed_chunk, updated_at
            )
            VALUES (
                :file_path, :status, :rows_inserted, :errors_encountered, :last_processed_chunk, NOW()
            )
            ON CONFLICT (file_path) DO UPDATE SET
                status = EXCLUDED.status,
                rows_inserted = EXCLUDED.rows_inserted,
                errors_encountered = EXCLUDED.errors_encountered,
                last_processed_chunk = EXCLUDED.last_processed_chunk,
                updated_at = NOW()
            """
        )
        payload = {
            "file_path": file_path,
            "status": status,
            "rows_inserted": rows_inserted,
            "errors_encountered": errors_encountered,
            "last_processed_chunk": last_processed_chunk,
        }
        with self.db.engine.begin() as connection:
            connection.execute(statement, payload)

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _ensure_table_columns(self, table_name: str, columns: Tuple[str, ...]) -> None:
        inspector = inspect(self.db.engine)
        if not inspector.has_table(table_name, schema="public"):
            return

        existing = {column["name"] for column in inspector.get_columns(table_name, schema="public")}
        missing = [column for column in columns if column not in existing]
        if not missing:
            return

        with self.db.engine.begin() as connection:
            for column in missing:
                quoted_table = self._quote_identifier(table_name)
                quoted_column = self._quote_identifier(column)
                column_type = "JSONB" if column == "votos_coaliciones" else "TEXT"
                statement = text(
                    f"ALTER TABLE public.{quoted_table} ADD COLUMN IF NOT EXISTS {quoted_column} {column_type}"
                )
                connection.execute(statement)

        logger.info(
            "[INFO] Esquema evolucionado | tabla=%s | columnas_agregadas=%s",
            table_name,
            len(missing),
        )

    def _process_file_with_checkpoint(self, file_path: Path, route: RouteDecision) -> Tuple[bool, int]:
        absolute_path = str(file_path.resolve(strict=False))
        checkpoint = self._get_checkpoint(absolute_path) or {}

        previous_rows = int(checkpoint.get("rows_inserted", 0) or 0)
        previous_errors = int(checkpoint.get("errors_encountered", 0) or 0)
        previous_last_chunk = int(checkpoint.get("last_processed_chunk", 0) or 0)

        rows_inserted = previous_rows
        errors_encountered = previous_errors
        last_chunk = previous_last_chunk

        if checkpoint.get("status") == "COMPLETED":
            return True, 0

        try:
            if route.target_table in self._FEDERAL_CANDIDATURAS_TABLES:
                rows_inserted = self.processor.process_candidaturas_federales(
                    csv_file_path=absolute_path,
                    table_name=route.target_table or "",
                )
                last_chunk = 1
                self._upsert_checkpoint(
                    file_path=absolute_path,
                    status="COMPLETED",
                    rows_inserted=rows_inserted,
                    errors_encountered=errors_encountered,
                    last_processed_chunk=last_chunk,
                )
                inserted_delta = rows_inserted - previous_rows
                return True, max(0, inserted_delta)

            for chunk_number, transformed_chunk in enumerate(
                self.processor.process_csv_chunks(
                    csv_path=file_path,
                    skiprows=route.skiprows,
                    sep=route.sep,
                    encoding=None,
                ),
                start=1,
            ):
                if chunk_number <= previous_last_chunk:
                    continue

                if not transformed_chunk.empty:
                    self._ensure_table_columns(
                        table_name=route.target_table or "",
                        columns=tuple(str(col) for col in transformed_chunk.columns),
                    )
                    to_sql_kwargs = {
                        "name": route.target_table or "",
                        "con": self.db.engine,
                        "schema": "public",
                        "if_exists": "append",
                        "index": False,
                        "method": "multi",
                        "chunksize": self.processor.chunk_size,
                    }
                    if "votos_coaliciones" in transformed_chunk.columns:
                        to_sql_kwargs["dtype"] = {"votos_coaliciones": JSONB}
                    transformed_chunk.to_sql(**to_sql_kwargs)
                    rows_inserted += len(transformed_chunk)

                last_chunk = chunk_number
                self._upsert_checkpoint(
                    file_path=absolute_path,
                    status="PARTIAL",
                    rows_inserted=rows_inserted,
                    errors_encountered=errors_encountered,
                    last_processed_chunk=last_chunk,
                )

            self._upsert_checkpoint(
                file_path=absolute_path,
                status="COMPLETED",
                rows_inserted=rows_inserted,
                errors_encountered=errors_encountered,
                last_processed_chunk=last_chunk,
            )
            inserted_delta = rows_inserted - previous_rows
            return True, max(0, inserted_delta)
        except Exception as exc:
            errors_encountered += 1
            self._upsert_checkpoint(
                file_path=absolute_path,
                status="FAILED",
                rows_inserted=rows_inserted,
                errors_encountered=errors_encountered,
                last_processed_chunk=last_chunk,
            )
            logger.exception("[ERROR] Fallo procesando %s: %s", absolute_path, exc)
            return False, 0

    def run(self, root_path: str | Path) -> DeltaReport:
        root = Path(root_path)
        if not root.exists():
            raise FileNotFoundError(f"Ruta raíz no encontrada: {root}")

        self.db.test_connection()
        self.ensure_checkpoint_table()

        report = DeltaReport()

        for csv_file in root.rglob("*.csv"):
            report.csv_found += 1

            decision = self.route_csv(csv_file)
            if decision.should_skip:
                report.ignored += 1
                logger.info("[INFO] Ignorado: %s | motivo=%s", csv_file, decision.reason)
                continue

            absolute_path = str(csv_file.resolve(strict=False))
            checkpoint = self._get_checkpoint(absolute_path)
            if checkpoint and checkpoint.get("status") == "COMPLETED":
                report.skipped_delta += 1
                logger.info("[INFO] Delta skip (COMPLETED): %s", absolute_path)
                continue

            ok, inserted_delta = self._process_file_with_checkpoint(csv_file, decision)
            if ok:
                report.processed_today += 1
                report.inserted_rows_today += inserted_delta
                logger.info(
                    "[INFO] Archivo procesado | tabla=%s | filas_insertadas_hoy=%s | archivo=%s",
                    decision.target_table,
                    inserted_delta,
                    absolute_path,
                )
            else:
                report.failures += 1

        return report


def main() -> None:
    root_2024 = Path(r"A:\proyectos\pt_nacional\x\año\2024")
    connector, ine_processor, _ = build_default_components(db_url=DEFAULT_DB_URL)
    manager = BatchIngestionManager(db=connector, processor=ine_processor)

    try:
        report = manager.run(root_2024)
        print(report.render())
    finally:
        connector.dispose()


if __name__ == "__main__":
    main()
