#!/usr/bin/env bash
# Stage 0 — Golden Baseline Protection.
#
# Restores a pg_dump custom-format (-Fc) backup, produced by
# infra/backup/backup_db.sh, into a target Postgres container.
#
# The dump is streamed into pg_restore over stdin (`docker exec -i ... <
# "$DUMP_FILE"`) rather than copied into the container as a file first —
# no container-internal path is ever passed as a command-line argument,
# which deliberately avoids Git-Bash/MSYS on Windows silently rewriting a
# path like /tmp/foo into a host path before it reaches the container.
#
# SAFETY: this is destructive to whatever already exists in the TARGET
# database (--clean drops existing objects before recreating them so the
# restore is exact, not additive). NEVER point TARGET_CONTAINER/DB_NAME at
# a database you care about unless you intend to overwrite it. For
# disaster-recovery onto a fresh Postgres instance this is exactly what you
# want; for a "restore test," always target an isolated throwaway
# container/database (see docs/21-disaster-recovery-and-rollback.md).
#
# Usage:
#   ./infra/backup/restore_db.sh /path/to/erp_nucleus_<ts>.dump
#   TARGET_CONTAINER=my-restore-postgres DB_NAME=erp_nucleus_restore_test \
#     ./infra/backup/restore_db.sh /path/to/erp_nucleus_<ts>.dump
#
# Env overrides:
#   TARGET_CONTAINER   Docker container running the target Postgres (default: erp-nucleus-postgres-1)
#   DB_USER             Postgres role to connect/restore as             (default: erp)
#   DB_NAME             Target database name                            (default: erp_nucleus)
set -euo pipefail

DUMP_FILE="${1:-}"
if [ -z "$DUMP_FILE" ]; then
  echo "Usage: $0 <path-to-dump-file>" >&2
  exit 1
fi
if [ ! -f "$DUMP_FILE" ]; then
  echo "ERROR: dump file not found: $DUMP_FILE" >&2
  exit 1
fi

TARGET_CONTAINER="${TARGET_CONTAINER:-erp-nucleus-postgres-1}"
DB_USER="${DB_USER:-erp}"
DB_NAME="${DB_NAME:-erp_nucleus}"

if ! docker inspect "$TARGET_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: container '$TARGET_CONTAINER' does not exist." >&2
  exit 1
fi
if [ "$(docker inspect -f '{{.State.Running}}' "$TARGET_CONTAINER")" != "true" ]; then
  echo "ERROR: container '$TARGET_CONTAINER' is not running." >&2
  exit 1
fi

echo "==> Target: database '${DB_NAME}' in container '${TARGET_CONTAINER}' (role '${DB_USER}')"
echo "==> This will DROP and recreate objects in '${DB_NAME}' to match the dump. Ctrl+C now to abort."
sleep 3

echo "==> Ensuring target database exists..."
docker exec "$TARGET_CONTAINER" psql -U "$DB_USER" -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 || \
  docker exec "$TARGET_CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE ${DB_NAME}"

echo "==> Restoring (pg_restore --clean --if-exists)..."
docker exec -i "$TARGET_CONTAINER" pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner < "$DUMP_FILE"

echo "==> Restore complete. Verifying alembic_version..."
docker exec "$TARGET_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tc "SELECT version_num FROM alembic_version;"
