import re
import unicodedata
from difflib import SequenceMatcher

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


class SemanticIntentEngine:
    def __init__(self):
        # 1. DICCIONARIO DE ENTIDADES (Con variantes sin acentos y coloquiales)
        self.entidades = {
            1: ["aguascalientes", "ags"],
            2: ["baja california", "bc", "baja norte"],
            3: ["baja california sur", "bcs", "baja sur"],
            4: ["campeche", "camp"],
            5: ["coahuila", "coah"],
            6: ["colima", "col"],
            7: ["chiapas", "chis"],
            8: ["chihuahua", "chih"],
            9: ["ciudad de mexico", "cdmx", "df", "distrito federal"],
            10: ["durango", "dgo"],
            11: ["guanajuato", "gto"],
            12: ["guerrero", "gro"],
            13: ["hidalgo", "hgo"],
            14: ["jalisco", "jal"],
            15: ["mexico", "edomex", "estado de mexico"],
            16: ["michoacan", "mich"],
            17: ["morelos", "mor"],
            18: ["nayarit", "nay"],
            19: ["nuevo leon", "nl"],
            20: ["oaxaca", "oax"],
            21: ["puebla", "pue"],
            22: ["queretaro", "qro"],
            23: ["quintana roo", "qroo", "q roo"],
            24: ["san luis potosi", "slp", "san luis"],
            25: ["sinaloa", "sin"],
            26: ["sonora", "son"],
            27: ["tabasco", "tab"],
            28: ["tamaulipas", "tamps"],
            29: ["tlaxcala", "tlax"],
            30: ["veracruz", "ver"],
            31: ["yucatan", "yuc"],
            32: ["zacatecas", "zac"],
        }

        # 2. DICCIONARIO DE CARGOS Y NIVELES
        self.cargos = {
            "AYUNTAMIENTO": [
                "ayuntamiento",
                "alcalde",
                "alcaldia",
                "presidencia municipal",
                "presidente municipal",
                "edil",
                "municipio",
                "regidor",
                "sindico",
            ],
            "GUBERNATURA": [
                "gobernador",
                "gubernatura",
                "gobierno",
                "gobenador",
                "gobernadora",
            ],
            "DIPUTACION_LOCAL": [
                "diputado local",
                "diputacion local",
                "congreso local",
                "diputados locales",
            ],
            "DIPUTACION_FEDERAL": [
                "diputado federal",
                "diputacion federal",
                "congreso de la union",
                "san lazaro",
                "diputados federales",
            ],
            "DIPUTACION": ["diputacion", "diputado", "diputados", "congreso"],
            "SENADURIA": ["senador", "senado", "senaduria", "escano", "senadores"],
            "PRESIDENCIA": [
                "presidente",
                "presidencia",
                "presidente de la republica",
                "amlo",
                "claudia",
                "xochitl",
                "maynez",
            ],
        }

        # 3. DICCIONARIO DE PARTIDOS
        self.partidos = {
            "MORENA": ["morena", "guinda", "4t", "cuarta transformacion"],
            "PAN": ["pan", "accion nacional", "blanquiazul", "derecha"],
            "PRI": ["pri", "revolucionario institucional", "tricolor"],
            "PRD": ["prd", "sol azteca"],
            "PT": ["pt", "partido del trabajo"],
            "PVEM": ["pvem", "verde", "verde ecologista", "partido verde"],
            "MC": ["mc", "movimiento ciudadano", "naranja", "fosfo"],
        }

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto removiendo acentos y ruido para matching robusto."""
        if not text:
            return ""
        text = text.lower()
        text = "".join(
            c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
        )
        text = text.replace("ñ", "n")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _orthographic_key(self, text: str) -> str:
        """
        Normaliza confusiones ortograficas comunes:
        - c/z/s -> s
        - h muda eliminada
        """
        text = self._normalize_text(text)
        text = re.sub(r"[cz]", "s", text)
        text = text.replace("h", "")
        return text

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _contains_alias(self, query: str, alias: str) -> bool:
        normalized_query = self._normalize_text(query)
        normalized_alias = self._normalize_text(alias)
        if not normalized_query or not normalized_alias:
            return False

        query_tokens = normalized_query.split()
        alias_tokens = normalized_alias.split()

        # Single token: usar matching por token para evitar falsos positivos ("pan" vs "pantalla")
        if len(alias_tokens) == 1:
            if normalized_alias in query_tokens:
                return True
            alias_key = self._orthographic_key(normalized_alias)
            for token in query_tokens:
                token_key = self._orthographic_key(token)
                if token_key == alias_key:
                    return True
                if self._similarity(token_key, alias_key) >= 0.85:
                    return True
            return False

        # Multi token: ventana deslizante con variante ortografica y fuzzy score.
        if len(query_tokens) < len(alias_tokens):
            query_candidates = [normalized_query]
        else:
            query_candidates = [
                " ".join(query_tokens[i : i + len(alias_tokens)])
                for i in range(len(query_tokens) - len(alias_tokens) + 1)
            ]

        alias_key = self._orthographic_key(normalized_alias)
        for candidate in query_candidates:
            if candidate == normalized_alias:
                return True
            candidate_key = self._orthographic_key(candidate)
            if candidate_key == alias_key:
                return True
            if self._similarity(candidate_key, alias_key) >= 0.86:
                return True
        return False

    async def parse_query(self, query: str, db_session: AsyncSession | AsyncConnection):
        normalized_query = self._normalize_text(query)

        intent = {
            "entidad_id": None,
            "municipio_id": None,
            "cargo_inferido": None,
            "partido_inferido": None,
            "distrito_local_id": None,
            "distrito_federal_id": None,
            "candidato_inferido": None,
            "accion": "flyTo",
            "bbox": None,
            "warning": None,
        }

        # Detección de Año (solo operamos 2024 por ahora).
        year_match = re.search(r"20\d\d", normalized_query)
        if year_match and year_match.group(0) != "2024":
            intent["warning"] = (
                f"El archivo historico {year_match.group(0)} esta en preparacion. Mostrando datos 2024."
            )

        # 1. Inferir Entidad
        for ent_id, aliases in self.entidades.items():
            if any(self._contains_alias(normalized_query, alias) for alias in aliases):
                intent["entidad_id"] = ent_id
                break

        # 2. Inferir Cargo
        for cargo_key, aliases in self.cargos.items():
            if any(self._contains_alias(normalized_query, alias) for alias in aliases):
                intent["cargo_inferido"] = cargo_key
                break

        # 3. Inferir Partido
        for partido_key, aliases in self.partidos.items():
            if any(self._contains_alias(normalized_query, alias) for alias in aliases):
                intent["partido_inferido"] = partido_key
                break

        # NUEVO: Detección de Distritos ultra-flexible (Soporta "distrito local 14" o "distrito 14 local")
        dl_match = re.search(r"distrito\s+(?:local\s+)?(\d+)(?:\s+local)?", normalized_query)
        if dl_match:
            intent["distrito_local_id"] = int(dl_match.group(1))

        df_match = re.search(r"distrito\s+(?:federal\s+)?(\d+)(?:\s+federal)?", normalized_query)
        if df_match:
            intent["distrito_federal_id"] = int(df_match.group(1))

        intent["candidato_inferido"] = None

        # NUEVO: Motor de Inferencia Nominal (Busqueda por nombre de Candidato)
        # Si la consulta tiene mas de 4 caracteres, buscamos si coincide con algun candidato
        if len(normalized_query) > 4:
            # Buscamos en el catalogo local (Ajusta el nombre de la tabla segun tu ingesta real)
            sql_candidato = sa.text(
                """
                SELECT actor_politico, id_entidad, id_municipio, id_distrito_local, tipo_candidatura
                FROM ine_candidaturas_local_2024
                WHERE unaccent(lower(actor_politico)) ILIKE :q OR unaccent(lower(candidato)) ILIKE :q
                LIMIT 1
            """
            )
            # Nota: Si PostgreSQL no tiene unaccent habilitado, el fallback es ILIKE normal:
            sql_candidato_fallback = sa.text(
                """
                SELECT actor_politico, id_entidad, id_municipio, id_distrito_local, tipo_candidatura
                FROM ine_candidaturas_local_2024
                WHERE actor_politico ILIKE :q OR candidato ILIKE :q
                LIMIT 1
            """
            )
            try:
                res_cand = await db_session.execute(sql_candidato_fallback, {"q": f"%{normalized_query}%"})
                cand_row = res_cand.fetchone()
                if cand_row:
                    intent["candidato_inferido"] = cand_row[0]
                    intent["entidad_id"] = cand_row[1]
                    if cand_row[2]:
                        intent["municipio_id"] = cand_row[2]
                    if cand_row[3]:
                        intent["distrito_local_id"] = cand_row[3]
                    intent["cargo_inferido"] = cand_row[4]
            except Exception as e:
                print(f"[!] Error en busqueda nominal: {e}")

        # ACTUALIZACIÓN FORENSE: Calcular Bounding Box DIRECTO desde la geometría maestra
        if intent["entidad_id"]:
            filtros_bbox = ["id_entidad = :ent_id"]
            params_bbox = {"ent_id": intent["entidad_id"]}

            # Usar identificadores si el motor de regex los detectó
            if intent["municipio_id"]:
                # Asumimos que dim_geo_secciones o la tabla geométrica tiene los IDs
                filtros_bbox.append(
                    "seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_municipio = :mun_id AND id_entidad = :ent_id)"
                )
                params_bbox["mun_id"] = intent["municipio_id"]
            if intent["distrito_local_id"]:
                filtros_bbox.append(
                    "seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_distrito_local = :dl_id AND id_entidad = :ent_id)"
                )
                params_bbox["dl_id"] = intent["distrito_local_id"]
            if intent["distrito_federal_id"]:
                filtros_bbox.append(
                    "seccion IN (SELECT seccion FROM dim_geo_secciones WHERE id_distrito_federal = :df_id AND id_entidad = :ent_id)"
                )
                params_bbox["df_id"] = intent["distrito_federal_id"]

            where_bbox = " AND ".join(filtros_bbox)

            # Consulta aislada: Nunca uses INNER JOIN con tablas de votos aquí.
            sql_bbox = sa.text(
                f"""
                SELECT ST_Extent(geometry)
                FROM geometria_secciones
                WHERE {where_bbox}
            """
            )

            try:
                result = await db_session.execute(sql_bbox, params_bbox)
                box_str = result.scalar()
                if box_str:
                    coords = re.findall(r"[-+]?\d*\.\d+|\d+", box_str)
                    if len(coords) == 4:
                        intent["bbox"] = [
                            float(coords[0]),
                            float(coords[1]),
                            float(coords[2]),
                            float(coords[3]),
                        ]
            except Exception as e:
                print(f"[!] Error calculando BBOX Geográfico: {e}")

        return intent
