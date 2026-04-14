from sqlalchemy import text

from etl_pipeline import DatabaseConnector, INEDataProcessor


def main() -> None:
    csv_path = r"A:\proyectos\pt_nacional\x\año\2024\local\AGS_PEL_2024\AYUNTAMIENTOS_csv\2024_SEE_AYUN_AGS_MUN.csv"
    table = "ine_ags_ayuntamientos_mun_muestra"

    db = DatabaseConnector()
    db.test_connection()

    with db.engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS public."{table}"'))

    processor = INEDataProcessor(db=db, chunk_size=10_000)
    rows = processor.load_csv_to_postgres(
        csv_path=csv_path,
        target_table=table,
        if_exists="replace",
        skiprows=0,
        sep=",",
        encoding="utf-8",
    )

    with db.engine.connect() as conn:
        db_rows = conn.execute(text(f'SELECT COUNT(*) FROM public."{table}"')).scalar_one()

    print(f"ROWS_INSERTED={rows}; ROWS_IN_TABLE={db_rows}")
    db.dispose()


if __name__ == "__main__":
    main()
