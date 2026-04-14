import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

DB_URI = "postgresql+asyncpg://admin:enterprise_password_2024@127.0.0.1:5454/elecciones_db"
engine = create_async_engine(DB_URI)


def int_cast_expr(column_sql: str) -> str:
    return f"NULLIF(regexp_replace({column_sql}::text, '[^0-9-]', '', 'g'), '')::INTEGER"


async def heal_geo_catalog():
    print("[*] Iniciando Auto-Curacion del Catalogo Geografico...")
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS dim_geo_secciones (
                    id_entidad INTEGER,
                    seccion INTEGER,
                    id_municipio INTEGER,
                    id_distrito_local INTEGER,
                    id_distrito_federal INTEGER,
                    PRIMARY KEY (id_entidad, seccion)
                );
                """
            )
        )

        await conn.execute(
            sa.text(
                f"""
                INSERT INTO dim_geo_secciones (id_entidad, seccion)
                SELECT DISTINCT {int_cast_expr('id_entidad')}, {int_cast_expr('seccion')}
                FROM geometria_secciones
                WHERE {int_cast_expr('id_entidad')} IS NOT NULL
                  AND {int_cast_expr('seccion')} IS NOT NULL
                ON CONFLICT DO NOTHING;
                """
            )
        )

        print("[*] Curando Municipios desde tabla de Ayuntamientos...")
        try:
            async with conn.begin_nested():
                await conn.execute(
                    sa.text(
                        f"""
                        UPDATE dim_geo_secciones d
                        SET id_municipio = v.mun
                        FROM (
                            SELECT {int_cast_expr('"ID_ESTADO"')} AS ent,
                                   {int_cast_expr('"SECCION"')} AS sec,
                                   MAX({int_cast_expr('"ID_MUNICIPIO"')}) AS mun
                            FROM ine_votos_local_ayun_2024
                            GROUP BY 1, 2
                        ) v
                        WHERE d.id_entidad = v.ent AND d.seccion = v.sec;
                        """
                    )
                )
        except Exception as e:
            print(f"[-] Aviso: {e}")

        print("[*] Curando Distritos Locales desde tabla de Diputaciones...")
        try:
            async with conn.begin_nested():
                await conn.execute(
                    sa.text(
                        f"""
                        UPDATE dim_geo_secciones d
                        SET id_distrito_local = v.dl
                        FROM (
                            SELECT {int_cast_expr('"ID_ESTADO"')} AS ent,
                                   {int_cast_expr('"SECCION"')} AS sec,
                                   MAX({int_cast_expr('"ID_DISTRITO_LOCAL"')}) AS dl
                            FROM ine_votos_local_dip_2024
                            GROUP BY 1, 2
                        ) v
                        WHERE d.id_entidad = v.ent AND d.seccion = v.sec;
                        """
                    )
                )
        except Exception as e:
            print(f"[-] Aviso: {e}")

        print("[*] Curando Distritos Federales...")
        try:
            async with conn.begin_nested():
                await conn.execute(
                    sa.text(
                        f"""
                        UPDATE dim_geo_secciones d
                        SET id_distrito_federal = v.df
                        FROM (
                            SELECT {int_cast_expr('"ID_ENTIDAD"')} AS ent,
                                   {int_cast_expr('"SECCION"')} AS sec,
                                   MAX({int_cast_expr('"ID_DISTRITO_FEDERAL"')}) AS df
                            FROM ine_votos_federal_dip_2024
                            GROUP BY 1, 2
                        ) v
                        WHERE d.id_entidad = v.ent AND d.seccion = v.sec;
                        """
                    )
                )
        except Exception as e:
            print(f"[-] Aviso: {e}")

    print("[+] Auto-Curacion completada. La tabla dim_geo_secciones esta lista para el HUD.")


if __name__ == "__main__":
    asyncio.run(heal_geo_catalog())
