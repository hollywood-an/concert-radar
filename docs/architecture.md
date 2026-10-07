# Architecture

Concert Radar finds concerts near a user by artists they follow and ranks the rest by taste.
Seven Python services cooperate through Kafka (Redpanda) topics, one gRPC call, and one
Postgres database; a Next.js app talks only to the gateway. Decisions behind this shape are in [`adr/`](adr/).

## System

```mermaid
flowchart LR
    TM[Ticketmaster<br/>Discovery API] --> scraper
    subgraph pipeline [Event pipeline]
        scraper[scraper-ticketmaster<br/>batch job] -- events.discovered --> deduper
        deduper -- events.deduped --> enricher
        enricher -- events.enriched --> matcher
        deduper -- events.status_changed --> notifier
        matcher -- matches.proposed --> notifier
    end
    MB[MusicBrainz] -.-> enricher
    SP[Spotify API] -.-> enricher
    scraper -. raw pages .-> S3[(S3<br/>raw archive)]

    web[Next.js web app] -- REST + WebSocket --> gateway
    gateway -- users.taste_updated --> matcher
    matcher -- matches.proposed --> gateway
    gateway -- gRPC GetRecommendations --> recommender

    deduper & enricher & matcher & notifier & gateway & recommender --> PG[(Postgres<br/>PostGIS + pgvector)]
    notifier --> mail[daily digest email]
```

| Service | What it does |
|---|---|
| `scraper-ticketmaster` | Batch job (an ECS Fargate task in production): pages through the Discovery API for one market (Columbus), archives each raw page to S3, publishes one `events.discovered` per show. |
| `deduper` | Upserts venues, events, and lineups idempotently; folds the same show listed by another source into one row (trigram title match, same venue, ±20 min, [ADR 004](adr/004-dedup-threshold.md)); publishes `events.deduped`, plus `events.status_changed` when a known show is cancelled or rescheduled. |
| `enricher` | Resolves each artist against MusicBrainz (1 req/s, retried on 503) and optionally Spotify, then embeds its genres with `all-MiniLM-L6-v2` (384 dimensions) so artists live in a shared taste space. |
| `matcher` | Decides who hears about what: a match needs an artist the user follows on the lineup of an upcoming show inside their radius ([ADR 006](adr/006-alert-rules.md)). Triggered by newly announced shows and by follows or home-area changes. |
| `notifier` | Queues matches and change notices, then sends one digest per user per day at 14:00 UTC. |
| `recommender` | gRPC server (`recommender.v1.RecommenderService`): nearby shows by artists the user doesn't follow yet, ranked by taste and spread across genres. Backs `GET /discover`. |
| `gateway` | FastAPI REST + WebSocket API: dev sign-in (JWT), ranked feed, discovery, search, follows, settings with address search, event and artist pages, and a live push of new matches. |
| `web` | Next.js 14, TypeScript, Redux Toolkit: feed with a Discover strip, clustered map, filters, event and artist pages, settings with a map picker and address search. |

## Ranking

The feed scores every upcoming headliner show within the user's travel radius per request
([ADR 002](adr/002-direct-sql-feed.md)):

```
score = 0.7 × cosine_similarity(user taste, artist genres) + 0.3 × e^(−days until show / 30)
```

A user's taste vector is the average embedding of the artists they follow, recomputed on
every follow (`update_user_taste_embedding`); with no follows the score is a neutral 0.5.
Artist pages list the six nearest artists by the same embedding, served by an HNSW index.

**Discovery** (the recommender, behind `GET /discover`) answers a different question: which
artists the user doesn't follow yet are worth a look. It takes each unfollowed headliner's
soonest upcoming show in range, skips dismissed shows, and ranks by cosine similarity alone.
To keep the list from being ten shades of one genre, at most two shows per primary genre come
first; the rest follow, so a small market still fills the list. The gateway calls it over gRPC
with a 2-second deadline and answers 503 if it's down or late, and the web app hides the strip
rather than waiting.

The contract is `proto/recommender/v1/recommender.proto`. CI runs `buf lint`, `buf format`,
and `buf breaking` against `main`, and regenerates the Python code (`proto/generate.sh`,
grpcio-tools + mypy-protobuf) to fail if the committed `src/gen/` copies are stale.

## Event flows

A newly announced show reaching a fan:

```mermaid
sequenceDiagram
    participant S as scraper
    participant D as deduper
    participant E as enricher
    participant M as matcher
    participant N as notifier
    participant G as gateway
    S->>D: events.discovered
    D->>D: upsert venue, event, lineup (new row)
    D->>E: events.deduped (is_new = true)
    E->>E: MusicBrainz lookup + genre embedding
    E->>M: events.enriched (is_new = true)
    M->>M: followers of a lineup artist, within radius, not dismissed
    M->>N: matches.proposed
    M->>G: matches.proposed
    G-->>G: push "New match" to the user's open WebSocket
    N->>N: queue in pending_alerts
    Note over N: 14:00 UTC: one digest email per user, recorded in alerts_sent
```

A follow, a Spotify import, or a change of home location runs the same path from the gateway:
it publishes `users.taste_updated` with the artists to re-match, and the matcher proposes
those artists' upcoming nearby shows. Shows a user was already emailed about are skipped by
`alerts_sent`. If such a show is later cancelled, postponed, or rescheduled, the deduper's
`events.status_changed` queues a change notice for the next digest.

## Kafka topics

Messages are JSON validated by Pydantic models in each service
([ADR 007](adr/007-json-messages.md)); producers attach W3C `traceparent` headers.

| Topic | Key | Producer | Consumers |
|---|---|---|---|
| `events.discovered` | `source:external_id` | scraper | deduper |
| `events.deduped` | event id | deduper | enricher |
| `events.enriched` | event id | enricher | matcher |
| `events.status_changed` | event id | deduper | notifier |
| `users.taste_updated` | user id | gateway | matcher |
| `matches.proposed` | `user:event` | matcher | notifier, gateway (live push) |
| `notifications.sent` | `user:event` | notifier | (analytics; none yet) |

`scraping.page_fetched` and `notifications.requested` from the original topic plan are
created but unused: raw pages go straight to S3, and the matcher hands matches to the notifier
directly.

## Data model

```mermaid
erDiagram
    users ||--o{ follows : has
    artists ||--o{ follows : "followed by"
    venues ||--o{ events : hosts
    events ||--o{ event_artists : lineup
    artists ||--o{ event_artists : plays
    users ||--o{ dismissals : hides
    events ||--o{ dismissals : ""
    users ||--o{ pending_alerts : queued
    users ||--o{ pending_show_changes : queued
    users ||--o{ alerts_sent : received
    events ||--o{ alerts_sent : ""

    users {
        uuid id
        text email
        geography home_location
        int travel_radius_m
        vector taste_embedding
        bool alert_email
    }
    artists {
        uuid id
        text name
        text mbid
        text_array genres
        vector embedding
    }
    venues {
        uuid id
        text name
        geography location
        jsonb source_ids
    }
    events {
        uuid id
        text source
        text external_id
        timestamptz starts_at
        event_status status
    }
```

Migrations are append-only SQL files applied by `db/migrate.sh`, which records each one in
`schema_migrations` and runs it in a single transaction.

## Deployment

```mermaid
flowchart LR
    dev[pull request] --> CI[GitHub Actions<br/>CI · Images · Terraform]
    CI -- merge to main --> deploy[Deploy workflow]
    deploy -- OIDC role, no stored keys --> ECR[(Amazon ECR)]
    deploy -- SSM Run Command --> host
    sched[EventBridge Scheduler<br/>every 6 h] -- RunTask --> task[ECS Fargate<br/>scraper task]
    task -- Kafka 19092 · OTLP 4317<br/>private network --> host
    task -- raw pages --> S3
    subgraph host [EC2 t3a.medium · Docker Compose]
        caddy[Caddy<br/>Let's Encrypt] --> webc[web] & gw[gateway] & jg[Jaeger UI]
        gw -- gRPC --> rec[recommender]
        workers[deduper · enricher<br/>matcher · notifier] --- rp[Redpanda] & db[(Postgres)]
    end
    host & task -- pull images --> ECR
    S3[(S3<br/>raw archive)]
    users((users)) -- HTTPS --> caddy
```

Terraform (`infra/terraform`) creates the host, its IAM role, the ECR repositories, the S3
bucket, the GitHub OIDC deploy role, the ECS cluster and roles for the scraper task, and its
schedule; there is no SSH (port 22 is closed; operators use SSM). The scraper's task
definition lives in the repo (`deploy/scraper-task.json`) and every deploy registers a new
revision with that commit's image; the schedule names the family without a revision, so it
always runs what is deployed. The task reaches Redpanda through a second listener on the
host's private address, which the host's security group opens only to the task's. See [`deploy/README.md`](../deploy/README.md) and
[ADR 005](adr/005-single-host-compose.md).

## Reliability

- **Idempotent consumers.** Every write is an upsert or `ON CONFLICT DO NOTHING`, so replaying
  a message changes nothing. Offsets are committed after each message is handled.
- **Crash, don't guess.** A malformed message is logged and skipped so a partition never wedges;
  anything else (database down, an unexpected bug) crashes the consumer, which restarts and
  resumes from its last committed offset.
- **Polite upstreams.** MusicBrainz is throttled to 1 request/second and 503s are retried with
  backoff; Ticketmaster 429s are retried the same way.
- **Health.** Every long-running service serves `/healthz` and `/readyz` (database reachable,
  consumer started or gRPC serving); the production stack waits on them during deploys.
- **Deadlines.** The gateway gives the recommender 2 seconds; a slow or missing recommender
  costs the Discover strip, never the feed. Nominatim (address search) is limited to one
  request a second across the gateway, with answers cached.

## Observability

OpenTelemetry traces cross service, Kafka, and gRPC boundaries: producers inject the trace
context into message headers (or gRPC metadata) and consumers continue it, so one trace follows a show from the scrape
through to the matcher (or a follow from the HTTP request to the queued alert). Logs are JSON
from `structlog` with `trace_id`, `span_id`, and `service_name` on every line. Jaeger runs in
the stack; in production its UI is behind basic auth.

## Testing

- Python services: integration tests against real Postgres (the production image), Redpanda,
  and MinIO through testcontainers; HTTP calls to MusicBrainz, Spotify, Ticketmaster, and
  Nominatim go through `httpx` mock transports. The recommender is tested over a real gRPC
  channel, and the gateway's `/discover` against an in-process gRPC server.
- Web: Vitest against the real Redux store and API client, with HTTP intercepted by MSW.
- CI runs ruff, `mypy --strict`, and every suite on each pull request, builds and smoke-tests
  every production image, and validates the Terraform; `main` only accepts green pull requests.
- `loadtest/feed.js` load-tests the feed with k6.

## Where this differs from the original spec

| Spec | Built | Why |
|---|---|---|
| Feed reads a materialized view | Direct SQL per request | [ADR 002](adr/002-direct-sql-feed.md) |
| Drizzle ORM in Next.js API routes | Web calls the gateway directly | [ADR 003](adr/003-gateway-is-the-api.md) |
| Kubernetes + Kustomize | One EC2 host, Docker Compose | [ADR 005](adr/005-single-host-compose.md) |
| Alerts above a score threshold, quiet hours | Followed artists only, daily digest | [ADR 006](adr/006-alert-rules.md) |
| Protobuf in `proto/` for every contract | JSON + Pydantic on Kafka; protobuf for the gRPC call | [ADR 007](adr/007-json-messages.md) |
| Mapbox GL JS | MapLibre GL with OpenStreetMap tiles | No API key or account needed |
| Ticketmaster DMA 249 | DMA 259 | 249 is Chicago; 259 is Columbus, OH |
| SES email | Logged email | SES sandbox only delivers to verified addresses |
| `postgis/postgis` + pgvector image | `pgvector/pgvector` + PostGIS | The bullseye-based PostGIS image no longer builds |
