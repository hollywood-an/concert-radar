#!/usr/bin/env bash
# Create every Kafka topic from the spec's topic table. Idempotent: existing topics are skipped.
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

cd "$(dirname "$0")/../.."
for topic in "${TOPICS[@]}"; do
  docker compose exec -T redpanda rpk topic create "$topic" --partitions 3 2>/dev/null \
    && echo "created $topic" \
    || echo "exists  $topic"
done
docker compose exec -T redpanda rpk topic list
