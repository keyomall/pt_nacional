# 🧠 MEMORY CORE: Sistema Operativo Electoral 2024
**DOCUMENTO DE RECUPERACIÓN DE CONTEXTO ABSOLUTO (HANDOVER PARA IA)**

> **⚠️ INSTRUCCIÓN CRÍTICA PARA CUALQUIER IA LECTORA:**
> Si acabas de abrir este proyecto o despertaste en un nuevo chat, **LEE ESTE DOCUMENTO DE PRINCIPIO A FIN**. Aquí se almacena la conciencia estructural del proyecto. No asumas ni reinventes nada. Todo el framework, puertos, lógicas de conexión y el punto exacto de pausa están aquí dictaminados.

---

## 1. IDENTIDAD DEL PROYECTO
- **Nombre:** Command Center Electoral 2024 (PT Nacional)
- **Tipo de Plataforma:** Sistema de Inteligencia y Análisis Forense Geo-Electoral de grado Enterprise.
- **Topología Central:** Motor de búsqueda semántica y mapeo vectorial (NLP) + Visualización de alta densidad por GPU.

## 2. ARQUITECTURA Y STACK TECNOLÓGICO (Fijado)
El proyecto usa un stack híbrido alojado localmente en Windows con Docker:

*   **Database (Docker):** PostgreSQL 16 + PostGIS 3 + pgvector v0.6.2 (Compilado en fuente).
    *   *Nota Crítica de Entorno:* El puerto mapeado es el **5454** en el Host (evadiendo colisón con un `postgres.exe` nativo de Windows en 5432).
    *   *Credenciales:* `postgresql://admin:enterprise_password_2024@127.0.0.1:5454/elecciones_db`
*   **Cache:** Redis 7-alpine (Puerto **6379**).
*   **Backend API (`/backend`):** FastAPI montado en Uvicorn. Interfaz en puerto **8000** (`http://127.0.0.1:8000`).
    *   *ORM:* SQLAlchemy 2.0 y GeoAlchemy2 integrados estructuralmente con un Connection Pool Estricto.
*   **Frontend Web (`/frontend`):** Next.js 15 (Turbopack desactivado para checkeos estrictos), React 19, TailwindCSS, Inter Font. Corriendo en el puerto **3000**.
    *   *Motores Render:* `deck.gl` + `react-map-gl` (MapLibre con style Carto Dark Matter).

## 3. ESTADO OPERACIONAL VERIFICADO (Punto de Pausa)
Hitos completados y certificados como exitosos (Exit Code 0) en la sesión anterior:
✅ Infraestructura Base (Docker-compose levantado, Postgres 16 operando).
✅ Next.js PWA Renderizada (Panel Deck.gl sin warnings TS ni violaciones de Inline CSS).
✅ FastAPI levantado y ORM SQLAlchemy integrado en `app/db.py` y `app/models.py`.
✅ Base de datos instanciada: La tabla base de Polígonos de Extensión `distritos_electorales` FUE CREADA y contiene columnas `geom` y `embedding_analitico`.

## 4. DEUDA TÉCNICA Y SIGUIENTE HITO (Roadmap Inmediato)
**ESTADO DE LOS DATOS:** Las tablas de la base de datos están *vacías*.

**➡️ 🛑 LA IA DEBE CONTINUAR DESDE ESTE PUNTO 🛑 ⬅️**
1. **Fase ETL (Ingesta de Datos):** Desarrollar un script en Python (o inyector FastAPI) para poblar la DB. Necesitamos leer los archivos shapefiles (o CSV/GeoJSON, p. ej. Base MAGAR / INE 2024) guardados localmente, procesarlos con `geopandas`/`pandas`, extraer lógicas y guardarlos sistemáticamente usando SQLAlchemy, incrustando la geometría espacial a SRID 4326.
2. **Fase API Endpoint:** Crear rutas REST (ej: `/api/v1/mapa/distritos`) en `main.py` que serialicen la tabla mediante GeoAlchemy/Shapely hacia formato `FeatureCollection` de GeoJSON compatible estrictamente para inyectar en la capa de Deck.GL.

## 5. CÓMO RENOVAR LA SESIÓN
Si reanudas tu trabajo:
1. Inicia **Docker Desktop** (Obligatorio). Usa terminal: `docker-compose up -d`.
2. Terminal Bash Python: `cd backend` -> `.\venv\Scripts\activate` -> `uvicorn app.main:app --reload --port 8000`.
3. Terminal Node: `cd frontend` -> `npm run dev`.

**ESTE ARCHIVO ES INMUTABLE SALVO EVOLUCIÓN ESTRUCTURAL DEL SISTEMA.**
