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
            "cargo_inferido": None,
            "partido_inferido": None,
            "accion": "flyTo",
            "bbox": None,
        }

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

        # 4. Calcular Bounding Box si hay entidad detectada
        if intent["entidad_id"]:
            sql = sa.text(
                """
                SELECT ST_Extent(geometry) as bbox
                FROM geometria_secciones
                WHERE id_entidad = :ent_id
                """
            )
            result = await db_session.execute(sql, {"ent_id": intent["entidad_id"]})
            box_str = result.scalar()

            if box_str:
                coords = re.findall(r"[-+]?\d*\.\d+|\d+", str(box_str))
                if len(coords) == 4:
                    intent["bbox"] = [float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])]

        return intent
