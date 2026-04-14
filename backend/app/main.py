from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Motor Electoral 2024 - API Espacial",
    description="Backend del Command Center Electoral con soporte GIS, búsqueda vectorial y análisis forense de datos.",
    version="1.0.0"
)

# Configuración estricta de CORS para el Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "Enterprise System Online",
        "modules": ["PostGIS", "pgvector", "NLP"],
        "version": "1.0.0"
    }


# TODO: Inyectar endpoints que devuelvan GeoJSON de Magar cruzados con INE
# Ejemplo futuro:
# @app.get("/api/v1/mapa/distritos")
# def get_distritos(): ...
