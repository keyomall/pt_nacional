import glob
import os
from typing import List

import geopandas as gpd
import pandas as pd
import pyogrio
from geoalchemy2 import Geometry
from shapely import make_valid
from sqlalchemy import create_engine, text

# Conexion estricta a la DB local del proyecto.
DB_URI = "postgresql://admin:enterprise_password_2024@127.0.0.1:5454/elecciones_db"
engine = create_engine(DB_URI)


def _normalize_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Homologa columnas de origen Magar a nomenclatura del sistema."""
    gdf.columns = [str(c).lower() for c in gdf.columns]

    rename_map = {}
    if "edon" in gdf.columns:
        rename_map["edon"] = "id_entidad"
    if "entidad" in gdf.columns:
        rename_map["entidad"] = "id_entidad"
    if "disn" in gdf.columns:
        rename_map["disn"] = "id_distrito_federal"
    if rename_map:
        gdf = gdf.rename(columns=rename_map)

    return gdf


def _repair_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repara geometrias invalidas para evitar fallos en PostGIS."""
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].apply(lambda geom: make_valid(geom) if geom is not None else None)
    gdf = gdf[~gdf.geometry.is_empty]
    gdf = gdf[gdf.geometry.notnull()]
    return gdf


def _select_seccional_files(repo_path: str) -> List[str]:
    shp_files = glob.glob(os.path.join(repo_path, "**", "*.shp"), recursive=True)
    return [
        shp
        for shp in shp_files
        if "seccion" in shp.lower()
        or "sec" in os.path.basename(shp).lower()
        or "censo2010" in shp.lower()
    ]


def process_magar_repository(repo_path: str, table_name: str = "geometria_secciones") -> None:
    print(f"[INFO] Escaneando repositorio de Magar en: {repo_path}")
    seccional_files = _select_seccional_files(repo_path)

    if not seccional_files:
        print("[WARN] No se encontraron shapefiles seccionales. Verifica la ruta.")
        return

    gdfs: List[gpd.GeoDataFrame] = []
    for shp in seccional_files:
        print(f"[INFO] Procesando: {os.path.basename(shp)}")
        try:
            # Tolerancia a geometrias corruptas de origen (anillos sin cierre).
            os.environ["OGR_GEOMETRY_ACCEPT_UNCLOSED_RING"] = "YES"
            gdf = pyogrio.read_dataframe(shp, on_invalid="ignore")
            gdf = _normalize_columns(gdf)

            if gdf.crs is None:
                print(f"[WARN] {os.path.basename(shp)} no tiene CRS. Se asume EPSG:4326.")
                gdf = gdf.set_crs(epsg=4326)
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)

            gdf = _repair_geometries(gdf)

            cols_to_keep = ["id_entidad", "seccion", "geometry"]
            available_cols = [c for c in cols_to_keep if c in gdf.columns]
            if "id_entidad" not in available_cols or "seccion" not in available_cols:
                print(
                    f"[WARN] {os.path.basename(shp)} omitido por falta de columnas "
                    f"requeridas (id_entidad/seccion)."
                )
                continue

            gdfs.append(gdf[available_cols])
        except Exception as exc:
            print(f"[ERROR] Error leyendo {shp}: {exc}")

    if not gdfs:
        print("[WARN] No se lograron extraer capas validas para secciones.")
        return

    print("[INFO] Concatenando capas seccionales nacionales...")
    master_gdf = pd.concat(gdfs, ignore_index=True)
    master_gdf = gpd.GeoDataFrame(master_gdf, geometry="geometry", crs="EPSG:4326")

    master_gdf["id_entidad"] = pd.to_numeric(master_gdf["id_entidad"], errors="coerce").astype("Int64")
    master_gdf["seccion"] = pd.to_numeric(master_gdf["seccion"], errors="coerce").astype("Int64")
    master_gdf = master_gdf.dropna(subset=["id_entidad", "seccion"])

    master_gdf = master_gdf.drop_duplicates(subset=["id_entidad", "seccion"], keep="first")
    print(f"[INFO] Subiendo {len(master_gdf)} poligonos a PostGIS...")

    master_gdf.to_postgis(
        table_name,
        engine,
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("GEOMETRY", srid=4326)},
    )

    with engine.begin() as conn:
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_geom ON {table_name} USING GIST (geometry)"))
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_ent_sec "
                f"ON {table_name} (id_entidad, seccion)"
            )
        )

    print("[INFO] Base espacial nacional inyectada y optimizada con exito.")


if __name__ == "__main__":
    # Ruta local del repositorio Magar descargado.
    MAGAR_REPO_PATH = r"A:\proyectos\pt_nacional\x\magar\mxDistritos"
    process_magar_repository(MAGAR_REPO_PATH)
