#!/usr/bin/env bash
set -euo pipefail

# Backs up the Postgres database with pg_dump, connecting directly over
# TCP. localhost:5432 (the default) reaches the database either way this
# project runs it: docker-compose.yml publishes that port from the
# postgres container, and it's the same port a native/local Postgres
# install listens on. Only the postgresql-client tools (pg_dump, psql,
# createdb, dropdb) plus gzip need to be on PATH -- no docker CLI
# dependency, so this works the same way regardless of how Postgres
# itself is running.
#
# Produces one timestamped, gzip-compressed plain-SQL dump per run under
# backups/, restorable with scripts/restore_db.sh (or, in a pinch, just
# `gunzip -c backups/foo.sql.gz | psql -d some_db`). Plain SQL rather
# than pg_dump's custom (-Fc) format so restoring needs nothing beyond
# psql -- one fewer tool to have installed and one fewer thing that can
# be missing when this escape hatch actually needs to be used. See
# docs/backups.md for the full picture: what a real deployment needs
# beyond this script, and how to run a restore drill.
#
# Usage: bash scripts/backup_db.sh
# Connection is configured via the root .env (POSTGRES_USER/PASSWORD/DB)
# or the standard PG* libpq env vars (PGHOST/PGPORT/PGUSER/PGPASSWORD),
# which always take precedence if set.

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
export PGUSER="${PGUSER:-${POSTGRES_USER:-postgres}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-postgres}}"
POSTGRES_DB="${POSTGRES_DB:-ai_commerce_os}"

for tool in pg_dump gzip; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: $tool not found on PATH." >&2
    exit 1
  fi
done

mkdir -p backups
timestamp="$(date -u +%Y%m%d_%H%M%S)"
out_file="backups/${POSTGRES_DB}_${timestamp}.sql.gz"

echo "Backing up database '$POSTGRES_DB' as '$PGUSER' from $PGHOST:$PGPORT..."

if ! pg_dump -d "$POSTGRES_DB" --no-owner --no-privileges | gzip > "$out_file"; then
  rm -f "$out_file"
  echo "Error: backup failed. Is Postgres running and reachable at $PGHOST:$PGPORT?" >&2
  exit 1
fi

size="$(du -h "$out_file" 2>/dev/null | cut -f1)"
echo "Backup written to $out_file (${size:-unknown size})"
