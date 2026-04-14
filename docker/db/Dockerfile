FROM postgres:16-bookworm

# Instalar PostGIS y dependencias de compilación para pgvector
RUN apt-get update && apt-get install -y \
    postgresql-16-postgis-3 \
    postgresql-16-postgis-3-scripts \
    postgresql-server-dev-16 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clonar y compilar pgvector v0.6.2
RUN cd /tmp && \
    git clone --branch v0.6.2 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make && \
    make install && \
    rm -rf /tmp/pgvector

# Scripts de inicialización para activar extensiones automáticamente
RUN echo "CREATE EXTENSION IF NOT EXISTS postgis;" > /docker-entrypoint-initdb.d/01_postgis.sql
RUN echo "CREATE EXTENSION IF NOT EXISTS vector;" > /docker-entrypoint-initdb.d/02_pgvector.sql
