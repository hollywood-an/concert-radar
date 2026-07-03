# Concert Radar

Concert discovery platform: follow artists (manually or via Spotify import), set a home
location and travel radius, and get alerts when matching shows are announced nearby. The
system scrapes ticketing platforms, resolves artists against MusicBrainz + Spotify, ranks
shows using taste embeddings + geo-proximity + recency decay, and pushes notifications.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 async, aiokafka
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Data**: PostgreSQL 16 (PostGIS + pgvector), Redpanda (Kafka), Redis, MinIO
- **Observability**: OpenTelemetry → Jaeger, structlog

## Quickstart

```bash
docker compose up -d          # Postgres, Redpanda, Redis, MinIO, Jaeger
./db/migrate.sh               # run all migrations
make seed                     # sample Columbus venues + artists  (or run seeds via db/migrate-style psql)
make dev-gateway              # REST gateway on :8000
make dev-web                  # Next.js on :3000
```

See `CONCERT_RADAR_SPEC.md` for the full build specification and `docs/` for architecture
notes.

## Services

| Service | Role |
|---|---|
| `services/gateway` | REST + WebSocket API for the frontend |
| `services/scraper-ticketmaster` | Scheduled scraper → `events.discovered` |
| `services/deduper` | Fuzzy dedup → `events.deduped` |
| `services/enricher` | MusicBrainz/Spotify resolution + embeddings → `events.enriched` |
| `services/matcher` | Relevance matching → `matches.proposed` |
| `services/notifier` | Alert delivery (email) → `notifications.sent` |
