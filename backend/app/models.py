from sqlalchemy import Column, Integer, String, Float, JSON
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from app.db import Base

class DistritoElectoral(Base):
    """
    Modelo fundacional que integra capacidades relacionales, espaciales (GIS)
    y de inteligencia artificial (NLP/Vectores).
    """
    __tablename__ = "distritos_electorales"

    id = Column(Integer, primary_key=True, index=True)
    # Metadatos del INE / MAGAR
    entidad_id = Column(Integer, index=True, nullable=False)
    distrito_id = Column(Integer, index=True, nullable=False)
    nombre = Column(String(100), index=True)
    
    # Análisis Forense - Stats Cache
    votos_totales = Column(Integer, default=0)
    ganador = Column(String(50), index=True)
    margen_victoria_pct = Column(Float, default=0.0)
    metricas_completas = Column(JSON, nullable=True) # Payload flexible para BI

    # Capa PostGIS: Geometría multipoligonal para alta resolución cartográfica
    # SRID 4326 (WGS 84) estándar web clásico para interactuar nativo con Deck.GL/PostGIS
    geom = Column(Geometry('MULTIPOLYGON', srid=4326))
    
    # Capa pgvector: Búsqueda Semántica
    # vector(384) para embeddings tipo all-MiniLM-L6-v2 (huggingface local model = óptimo/rápido)
    embedding_analitico = Column(Vector(384))
