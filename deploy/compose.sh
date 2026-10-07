#!/usr/bin/env bash
# docker compose for the production stack, with the settings deploy/deploy.sh wrote.
# Use it for everything on the host, for example:
#   deploy/compose.sh ps
#   deploy/compose.sh logs -f --tail 100 gateway
#   deploy/compose.sh --profile jobs run --rm scraper   # what EventBridge Scheduler runs
set -euo pipefail

ENV_FILE="${CONCERT_RADAR_ENV_FILE:-/opt/concert-radar/.env.deploy}"
cd "$(dirname "$0")"
exec docker compose -f compose.prod.yml --env-file "$ENV_FILE" "$@"
