# Sistema Operativo Electoral 2024

Command Center de inteligencia electoral con mapas renderizados por GPU (Deck.gl), backend Python (FastAPI) y base de datos PostgreSQL híbrida (PostGIS + pgvector).

## Stack Tecnológico

- **Frontend**: Next.js + Deck.gl + MapLibre GL (renderizado GPU)
- **Backend**: FastAPI + GeoAlchemy2 + pgvector
- **Base de Datos**: PostgreSQL 16 + PostGIS 3 + pgvector
- **Cache**: Redis 7
- **Contenedores**: Docker + Docker Compose

## Módulos

- `frontend/` — Command Center visual (mapas, análisis, búsqueda semántica)
- `backend/` — API REST espacial (GeoJSON, NLP, vectores)
- `docker/db/` — Imagen personalizada PostgreSQL con PostGIS y pgvector

## Levantar el Sistema

```bash
# Infraestructura DB + Redis
docker-compose up -d --build

# Backend (en /backend)
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Frontend (en /frontend)
npm run dev
```

## Endpoints API

- `GET /api/health` — Estado del sistema
- `GET /api/v1/mapa/distritos` — GeoJSON de distritos electorales
