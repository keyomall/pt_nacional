import logging
from typing import Any
from types import SimpleNamespace

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
                FROM dim_geo_secciones
                WHERE id_entidad = :ent AND seccion = :sec
                LIMIT 1
                """
            )
            res_geo = await db.execute(sql_geo, {"ent": entidad, "sec": seccion})
            geo_row = res_geo.fetchone()
            geo = geo_row._mapping if geo_row else {}
            geo_ns = SimpleNamespace(**geo) if geo else SimpleNamespace()

            if not geo and cargo_key != "PRESIDENCIA":
                return {"candidato": "Geometría huérfana", "detalle": "Sin mapeo de casilla"}

            # --- MODULO DE RESOLUCION DE INDEPENDIENTES (CI) ---
            partido_upper = partido.upper().strip()
            is_independent = "CI" in partido_upper or "INDEP" in partido_upper

            if is_independent:
                condicion_partido_fed = "(partido_ci ILIKE '%INDEP%' OR partido_ci ILIKE '%CI%')"
                condicion_partido_loc = "(actor_politico ILIKE '%INDEP%' OR actor_politico ILIKE '%CI%')"
                params = {"ent": entidad}
            else:
                condicion_partido_fed = "partido_ci ILIKE :p"
                condicion_partido_loc = "actor_politico ILIKE :p"
                params = {"ent": entidad, "p": f"%{partido}%"}

            # --- BUSQUEDA NOMINAL BLINDADA ---
            if cargo_key == "PRESIDENCIA":
                sql = sa.text(f"SELECT propietario FROM {tabla_catalogo} WHERE {condicion_partido_fed} LIMIT 1")
                res = await db.execute(sql, params)
                row = res.fetchone()
                if row:
                    resultado = {"candidato": row[0], "detalle": "Candidatura Nacional"}

            elif cargo_key == "SENADURIA":
                sql = sa.text(
                    f"""
                    SELECT propietarios, suplentes FROM {tabla_catalogo}
                    WHERE id_entidad = :ent AND {condicion_partido_fed} LIMIT 1
                """
                )
                res = await db.execute(sql, params)
                row = res.fetchone()
                if row:
                    prop = row[0] if isinstance(row[0], str) else ", ".join(row[0])
                    resultado = {"candidato": "Fórmula Senatorial", "detalle": prop[:100]}

            elif cargo_key == "DIPUTACION_FEDERAL":
                sql = sa.text(
                    f"""
                    SELECT propietario FROM {tabla_catalogo}
                    WHERE id_entidad = :ent AND id_distrito_federal = :dist AND {condicion_partido_fed} LIMIT 1
                """
                )
                params["dist"] = getattr(geo_ns, "id_distrito_federal", 0)
                res = await db.execute(sql, params)
                row = res.fetchone()
                if row:
                    resultado = {"candidato": row[0], "detalle": f"Distrito Federal {params['dist']}"}

            elif cargo_key in ["AYUNTAMIENTO", "GUBERNATURA", "DIPUTACION_LOCAL"]:
                filtros_adicionales = []

                # FIX: Filtro estricto para Alcaldías/Ayuntamientos
                if cargo_key == "AYUNTAMIENTO":
                    mun_id = getattr(geo_ns, "id_municipio", None)
                    if mun_id:
                        filtros_adicionales.append("id_municipio = :mun")
                        params["mun"] = mun_id

                # FIX CRÍTICO: Filtro estricto para Diputaciones Locales
                elif cargo_key == "DIPUTACION_LOCAL":
                    dl_id = getattr(geo_ns, "id_distrito_local", None)
                    if dl_id:
                        filtros_adicionales.append("id_distrito_local = :dl")
                        params["dl"] = dl_id

                where_extra = " AND " + " AND ".join(filtros_adicionales) if filtros_adicionales else ""

                # EXTRACCIÓN DE ORIGEN PARTIDISTA: Traemos la columna partido_origen
                sql = sa.text(
                    f"""
                    SELECT candidato, tipo_candidatura, partido_origen FROM {tabla_catalogo}
                    WHERE id_entidad = :ent {where_extra} AND {condicion_partido_loc}
                """
                )

                res = await db.execute(sql, params)
                rows = res.fetchall()

                if rows:
                    if cargo_key == "AYUNTAMIENTO":
                        # Búsqueda heurística tolerante: Busca PRES, ALC, PM_
                        pres_row = next((r for r in rows if any(k in str(r[1]).upper() for k in ["PRES", "ALC", "PM_"])), None)

                        candidato_final = pres_row[0] if pres_row else rows[0][0]
                        origen_final = pres_row[2] if pres_row else rows[0][2]

                        siglado = f" | Origen: {origen_final}" if origen_final and str(origen_final).strip() != "nan" else ""

                        resultado = {
                            "candidato": candidato_final,
                            "detalle": f"Planilla Ganadora ({len(rows)} pos.){siglado}",
                        }
                    else:
                        candidato_final = rows[0][0]
                        origen_final = rows[0][2]

                        siglado = f"Origen Partidista: {origen_final}" if origen_final and str(origen_final).strip() != "nan" else "Candidatura Local/Estatal"
                        resultado = {"candidato": candidato_final, "detalle": siglado}

        except Exception as exc:
            logger.error("[!] Error resolviendo identidad nominal: %s", exc)
            return {"candidato": "Error de catálogo", "detalle": "Resolución SQL fallida"}

        return resultado
