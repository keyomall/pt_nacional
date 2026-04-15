import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CandidatoEDI(Base):
    __tablename__ = "edi_candidatos"

    id = sa.Column(sa.String, primary_key=True)  # UUID
    nombre_completo = sa.Column(sa.String, nullable=False, index=True)
    alias = sa.Column(sa.String)
    partido_actual = sa.Column(sa.String)
    biografia = sa.Column(sa.Text)
    telefono = sa.Column(sa.String)
    redes_sociales = sa.Column(sa.JSON)  # {"twitter": "...", "facebook": "..."}
    foto_perfil_url = sa.Column(sa.String)  # Ruta a la imagen sin fondo
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())


class TrayectoriaEDI(Base):
    __tablename__ = "edi_trayectoria"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    candidato_id = sa.Column(sa.String, sa.ForeignKey("edi_candidatos.id"))
    anio = sa.Column(sa.Integer)
    cargo = sa.Column(sa.String)
    partido_siglado = sa.Column(sa.String)
    coalicion = sa.Column(sa.String)
    resultado = sa.Column(sa.String)  # "VICTORIA", "DERROTA"
