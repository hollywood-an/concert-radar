#!/usr/bin/env bash
# Runs all migrations in db/migrations/ in filename order.
# Uses local psql when available, otherwise falls back to psql inside the
# docker compose postgres container (dev machines often lack psql).
set -euo pipefail
cd "$(dirname "$0")/.."

DATABASE_URL_SYNC="${DATABASE_URL_SYNC:-postgresql://cr:cr_dev@localhost:5433/concertradar}"

run_sql_file() {
  if command -v psql >/dev/null 2>&1; then
    psql "$DATABASE_URL_SYNC" -v ON_ERROR_STOP=1 -f "$1"
  else
    docker compose exec -T postgres psql -U cr -d concertradar -v ON_ERROR_STOP=1 <"$1"
  fi
}

for f in db/migrations/*.sql; do
  echo "Running $f..."
  run_sql_file "$f"
done
echo "All migrations applied."
