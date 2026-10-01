#!/usr/bin/env bash
# Applies the migrations in db/migrations/ that this database has not run yet, in
# filename order, recording each one in schema_migrations. Every file runs in a single
# transaction together with its schema_migrations row, so a failing migration leaves
# neither a partial schema change nor a record behind.
#
#   db/migrate.sh                     apply every migration not yet recorded
#   db/migrate.sh --baseline <file>   record <file> and every migration before it as
#                                     applied without running them (for a database that
#                                     was migrated before tracking existed)
#
# Uses local psql when available, otherwise psql inside the docker compose postgres
# container (dev machines often lack psql).
set -euo pipefail
cd "$(dirname "$0")/.."

DATABASE_URL_SYNC="${DATABASE_URL_SYNC:-postgresql://cr:cr_dev@localhost:5433/concertradar}"

psql_cmd() {
  if command -v psql >/dev/null 2>&1; then
    psql "$DATABASE_URL_SYNC" -X -q -v ON_ERROR_STOP=1 "$@"
  else
    docker compose exec -T postgres psql -U cr -d concertradar -X -q -v ON_ERROR_STOP=1 "$@"
  fi
}

query() {
  psql_cmd -tA -c "SET client_min_messages = warning" -c "$1"
}

query "CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"

if [[ "${1:-}" == "--baseline" ]]; then
  target="$(basename "${2:?usage: db/migrate.sh --baseline <migration filename>}")"
  [[ -f "db/migrations/$target" ]] || { echo "no such migration: $target" >&2; exit 1; }
  for f in db/migrations/*.sql; do
    name="$(basename "$f")"
    [[ "$name" > "$target" ]] && break
    query "INSERT INTO schema_migrations (filename) VALUES ('$name') ON CONFLICT DO NOTHING"
    echo "Recorded $name as applied (not run)."
  done
  exit 0
fi

applied="$(query "SELECT filename FROM schema_migrations")"
if [[ -z "$applied" && "$(query "SELECT to_regclass('public.artists') IS NOT NULL")" == "t" ]]; then
  echo "This database already has the schema but no migration history." >&2
  echo "Record what it has with: db/migrate.sh --baseline <last applied migration>" >&2
  exit 1
fi

count=0
for f in db/migrations/*.sql; do
  name="$(basename "$f")"
  grep -qxF "$name" <<<"$applied" && continue
  echo "Applying $name..."
  { cat "$f"; printf "\nINSERT INTO schema_migrations (filename) VALUES ('%s');\n" "$name"; } \
    | psql_cmd -1 -f -
  count=$((count + 1))
done
if ((count == 0)); then
  echo "Up to date."
else
  echo "Applied $count migration(s)."
fi
