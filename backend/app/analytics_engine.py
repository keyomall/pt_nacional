import logging
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger("AnalyticsEngine")

# Mapeo controlado de catálogos (whitelist anti-inyección).
CATALOGOS_CANDIDATURAS = {
    "PRESIDENCIA": "ine_candidaturas_federal_pres_2024",
    "SENADURIA": "ine_candidaturas_federal_sen_2024",
    "DIPUTACION_FEDERAL": "ine_candidaturas_federal_dip_2024",
    "GUBERNATURA": "ine_candidaturas_local_2024",
    "AYUNTAMIENTO": "ine_candidaturas_local_2024",
    "DIPUTACION_LOCAL": "ine_candidaturas_local_2024",
}


class AnalyticsEngine:
    async def get_winner_identity(
        self,
        cargo: str,
        entidad: int,
        seccion: int,
        partido: str,
        db: Any,
    ) -> dict[str, str]:
        cargo_key = cargo.upper()
        tabla_catalogo = CATALOGOS_CANDIDATURAS.get(cargo_key)
        resultado = {
            "candidato": "Sin registro",
            "detalle": "Múltiples fuerzas o coalición compleja",
        }

        if not tabla_catalogo:
            return resultado

        try:
            # 1) Resolver llaves geográficas base desde sección.
            sql_geo = sa.text(
                """
                SELECT id_municipio, id_distrito_federal, id_distrito_local
                FROM eleccion_2024_casillas
                WHERE id_entidad = :ent AND seccion = :sec
                LIMIT 1
                """
            )
            res_geo = await db.execute(sql_geo, {"ent": entidad, "sec": seccion})
            geo_row = res_geo.fetchone()
            geo = geo_row._mapping if geo_row else {}

            if not geo and cargo_key != "PRESIDENCIA":
                return {"candidato": "Geometría huérfana", "detalle": "Sin mapeo de casilla"}

            # 2) Resolución nominal por cargo.
            partido_like = f"%{partido}%"

            if cargo_key == "PRESIDENCIA":
                sql = sa.text(
                    f"SELECT propietario FROM {tabla_catalogo} WHERE partido_ci ILIKE :p LIMIT 1"
                )
                row = (await db.execute(sql, {"p": partido_like})).fetchone()
                if row:
                    return {"candidato": str(row[0]), "detalle": "Candidatura Nacional"}

            if cargo_key == "SENADURIA":
                sql = sa.text(
                    f"""
                    SELECT propietarios, suplentes
                    FROM {tabla_catalogo}
                    WHERE id_entidad = :ent AND partido_ci ILIKE :p
                    LIMIT 1
                    """
                )
                row = (await db.execute(sql, {"ent": entidad, "p": partido_like})).fetchone()
                if row:
                    propietarios = row[0]
                    if isinstance(propietarios, list):
                        propietarios_txt = ", ".join(str(x) for x in propietarios)
                    else:
                        propietarios_txt = str(propietarios)
                    return {
                        "candidato": "Fórmula Senatorial",
                        "detalle": propietarios_txt[:140],
                    }

            if cargo_key == "DIPUTACION_FEDERAL":
                sql = sa.text(
                    f"""
                    SELECT propietario
                    FROM {tabla_catalogo}
                    WHERE id_entidad = :ent
                      AND id_distrito_federal = :dist
                      AND partido_ci ILIKE :p
                    LIMIT 1
                    """
                )
                distrito = int(geo.get("id_distrito_federal") or 0)
                row = (
                    await db.execute(
                        sql,
                        {"ent": entidad, "dist": distrito, "p": partido_like},
                    )
                ).fetchone()
                if row:
                    return {
                        "candidato": str(row[0]),
                        "detalle": f"Distrito Federal {distrito if distrito else 'N/A'}",
                    }

            if cargo_key in {"AYUNTAMIENTO", "GUBERNATURA", "DIPUTACION_LOCAL"}:
                filtro_adicional = "AND id_municipio = :mun" if cargo_key == "AYUNTAMIENTO" else ""
                sql = sa.text(
                    f"""
                    SELECT candidato, tipo_candidatura
                    FROM {tabla_catalogo}
                    WHERE id_entidad = :ent
                      {filtro_adicional}
                      AND actor_politico ILIKE :p
                    """
                )
                params: dict[str, Any] = {"ent": entidad, "p": partido_like}
                if cargo_key == "AYUNTAMIENTO":
                    params["mun"] = int(geo.get("id_municipio") or 0)

                rows = (await db.execute(sql, params)).fetchall()
                if rows:
                    if cargo_key == "AYUNTAMIENTO":
                        presidente = next(
                            (
                                str(r[0])
                                for r in rows
                                if "PRES" in str(r[1]).upper()
                            ),
                            None,
                        )
                        return {
                            "candidato": presidente or "Planilla Ganadora",
                            "detalle": f"Planilla de {len(rows)} posiciones (Cabildo)",
                        }
                    return {"candidato": str(rows[0][0]), "detalle": "Candidatura Local"}

        except Exception as exc:
            logger.error("[!] Error resolviendo identidad nominal: %s", exc)
            return {"candidato": "Error de catálogo", "detalle": "Resolución SQL fallida"}

        return resultado
