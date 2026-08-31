#!/usr/bin/env bash
set -euo pipefail

# Restores a backup produced by scripts/backup_db.sh, connecting directly
# over TCP (see scripts/backup_db.sh for why this needs no docker CLI
# dependency -- same reasoning applies here).
#
# DESTRUCTIVE: drops and recreates the target database before restoring,
# so anything currently in it is lost. Requires typed confirmation unless
# -y/--yes is passed. Stop the app (uvicorn/frontend) first -- an open
# connection can block the drop.
#
# Usage: bash scripts/restore_db.sh [-y|--yes] <backup-file>
#   <backup-file>  a .sql.gz file created by scripts/backup_db.sh (a
#                  plain .sql also works, gzipped or not -- detected by
#                  extension)
#   -y, --yes      skip the confirmation prompt (for non-interactive use)
#
# See docs/backups.md for the full picture, including how to run this as
# a periodic restore drill against a scratch database (point POSTGRES_DB
# at a throwaway name rather than the real one to try it safely).

usage() {
  echo "Usage: $0 [-y|--yes] <backup-file>" >&2
  exit 1
}

skip_confirm=false
backup_file=""
for arg in "$@"; do
  case "$arg" in
    -y|--yes) skip_confirm=true ;;
    -h|--help) usage ;;
    *) backup_file="$arg" ;;
  esac
done

[ -n "$backup_file" ] || usage
[ -f "$backup_file" ] || { echo "Error: backup file not found: $backup_file" >&2; exit 1; }

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

for tool in dropdb createdb psql; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: $tool not found on PATH." >&2
    exit 1
  fi
done

if [ "$skip_confirm" != true ]; then
  echo "This will DROP and recreate database '$POSTGRES_DB' on $PGHOST:$PGPORT and restore it from:"
  echo "  $backup_file"
  echo "All current data in '$POSTGRES_DB' will be permanently lost."
  read -r -p "Type 'yes' to continue: " confirmation
  if [ "$confirmation" != "yes" ]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "Dropping and recreating '$POSTGRES_DB'..."
dropdb --if-exists "$POSTGRES_DB"
createdb "$POSTGRES_DB"

echo "Restoring from $backup_file..."
case "$backup_file" in
  *.gz) gunzip -c "$backup_file" | psql -q -d "$POSTGRES_DB" ;;
  *) psql -q -d "$POSTGRES_DB" < "$backup_file" ;;
esac

echo "Restore complete."
echo "If this backup predates a newer migration, run 'alembic upgrade head' from backend/ next."
