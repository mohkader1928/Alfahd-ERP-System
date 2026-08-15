#!/usr/bin/env bash
# Stage 0 — Golden Baseline Protection.
#
# Takes a full logical backup (schema + data) of the ERP Postgres database
# using pg_dump's custom format (-Fc), which supports selective/parallel
# restore via pg_restore and is Postgres's own recommended format for
# anything beyond a toy `psql < dump.sql`.
#
# pg_dump writes to stdout inside the container; `docker exec` streams that
# straight back to the host shell, which redirects it into a real file.
# No intermediate file is ever written inside the container, and no
# container-internal path is ever passed as a command-line argument — this
# deliberately sidesteps Git-Bash/MSYS's automatic POSIX-to-Windows path
# rewriting (a real footgun on Windows: an argument like /tmp/foo silently
# becomes C:\Users\...\Temp\foo before it reaches `docker exec`, which then
# breaks INSIDE the Linux container where that Windows path means nothing).
#
# Read-only against the source database — pg_dump takes a consistent MVCC
# snapshot and never blocks/mutates the source. Safe to run against a live
# database at any time.
#
# Usage:
#   ./infra/backup/backup_db.sh
#   CONTAINER=my-postgres DB_USER=erp DB_NAME=erp_nucleus ./infra/backup/backup_db.sh
#
# Env overrides (all optional, defaults match infra/docker-compose.yml):
#   CONTAINER   Docker container running Postgres (default: erp-nucleus-postgres-1)
#   DB_USER     Postgres role to connect as                (default: erp)
#   DB_NAME     Database to back up                         (default: erp_nucleus)
#   OUT_DIR     Where to write the .dump file on the host    (default: infra/backup/artifacts)
set -euo pipefail

CONTAINER="${CONTAINER:-erp-nucleus-postgres-1}"
DB_USER="${DB_USER:-erp}"
DB_NAME="${DB_NAME:-erp_nucleus}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${OUT_DIR:-$SCRIPT_DIR/artifacts}"

mkdir -p "$OUT_DIR"

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: container '$CONTAINER' does not exist. Is the stack up? (docker compose -f infra/docker-compose.yml ps)" >&2
  exit 1
fi

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" != "true" ]; then
  echo "ERROR: container '$CONTAINER' is not running." >&2
  exit 1
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="erp_nucleus_${TIMESTAMP}.dump"
HOST_PATH="${OUT_DIR}/${FILENAME}"

echo "==> Backing up '${DB_NAME}' from container '${CONTAINER}' as user '${DB_USER}'..."
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$HOST_PATH"

if [ ! -s "$HOST_PATH" ]; then
  echo "ERROR: backup file is missing or empty: $HOST_PATH" >&2
  exit 1
fi

# Sanity check: pg_restore can list the archive's table of contents without
# actually restoring anything — proves the dump file is structurally valid,
# not just non-empty. Feeds the host file back in over stdin, so again no
# container-side path argument is involved.
if ! docker exec -i "$CONTAINER" pg_restore --list < "$HOST_PATH" > /dev/null 2>&1; then
  echo "ERROR: pg_restore could not read the table of contents of $HOST_PATH — dump may be corrupt." >&2
  exit 1
fi

SHA256=""
if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$HOST_PATH" | cut -d' ' -f1)"
  echo "$SHA256  $FILENAME" > "${HOST_PATH}.sha256"
fi

SIZE_BYTES="$(stat -c%s "$HOST_PATH" 2>/dev/null || stat -f%z "$HOST_PATH" 2>/dev/null || echo unknown)"

echo "==> Backup complete."
echo "    File:    $HOST_PATH"
echo "    Size:    ${SIZE_BYTES} bytes"
[ -n "$SHA256" ] && echo "    SHA256:  $SHA256"
echo "    Verify:  docker exec -i <any-postgres-container> pg_restore --list < \"$HOST_PATH\""
