# Dev Postgres image: the schema needs BOTH PostGIS and pgvector, and no official
# image ships both (pgvector/pgvector lacks postgis.control). Start from postgis
# and add pgvector from the PGDG apt repo already configured in that image.
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
