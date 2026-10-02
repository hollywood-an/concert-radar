#!/usr/bin/env bash
# Create every Kafka topic from the spec's topic table. Idempotent: existing topics are skipped.
# Uses rpk directly when it is on PATH (the production `topics` job runs inside a Redpanda
# container, with RPK_BROKERS pointing at the broker), otherwise rpk inside the docker
# compose redpanda container (dev).
set -euo pipefail

TOPICS=(
  scraping.page_fetched
  events.discovered
  events.deduped
  events.enriched
  events.status_changed
  users.taste_updated
  matches.proposed
  notifications.requested
  notifications.sent
)

if command -v rpk >/dev/null 2>&1; then
  rpk_cmd() { rpk "$@" -X brokers="${RPK_BROKERS:-localhost:9092}"; }
else
  cd "$(dirname "$0")/../.."
  rpk_cmd() { docker compose exec -T redpanda rpk "$@"; }
fi

for topic in "${TOPICS[@]}"; do
  rpk_cmd topic create "$topic" --partitions 3 >/dev/null 2>&1 \
    && echo "created $topic" \
    || echo "exists  $topic"
done
rpk_cmd topic list
