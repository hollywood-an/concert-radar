# Postgres image for dev, tests, and production: the schema needs BOTH pgvector and
# PostGIS, and no official image ships both. Start from pgvector's image (bookworm,
# published for amd64 and arm64) and add PostGIS from the PGDG apt repo it already has.
# The previous base, postgis/postgis:16-3.4, is Debian bullseye, which PGDG no longer
# serves, so it can no longer be built.
FROM pgvector/pgvector:0.8.6-pg16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16-postgis-3 \
        postgresql-16-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
