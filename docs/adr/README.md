# Architecture decision records

Short records of the decisions that shaped Concert Radar, especially where the build departs
from [`CONCERT_RADAR_SPEC.md`](../../CONCERT_RADAR_SPEC.md). Each has a status, the context
that forced a choice, the decision, and its consequences.

| ADR | Decision |
|---|---|
| [001](001-redpanda-over-kafka.md) | Run Redpanda as the Kafka broker |
| [002](002-direct-sql-feed.md) | Serve the feed with direct SQL, not a materialized view |
| [003](003-gateway-is-the-api.md) | The gateway is the only API; no ORM in the web app |
| [004](004-dedup-threshold.md) | Treat listings as one show at trigram similarity > 0.6, same venue, ±20 minutes |
| [005](005-single-host-compose.md) | Deploy to one EC2 host with Docker Compose |
| [006](006-alert-rules.md) | Alert only on followed artists, once a day |
| [007](007-json-messages.md) | JSON messages with Pydantic contracts on Kafka |
