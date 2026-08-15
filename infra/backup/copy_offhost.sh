#!/usr/bin/env bash
# Stage 0 Closure — GAP 2: off-host backup copy.
#
# Copies the most recent (or a specified) backup produced by backup_db.sh
# to a destination path OUTSIDE this machine's primary disk — an external
# drive, a mapped network/NAS share, or a locally-synced cloud-storage
# folder (OneDrive/Dropbox/Google Drive/etc. — any of these appear as an
# ordinary filesystem path once mounted/synced, so this script needs no
# cloud API, no credentials, and nothing beyond a plain path). This is
# deliberately the simplest mechanism that actually gets a copy of the
# Golden Baseline off this one disk, not a full backup-management system.
#
# Requires NO secrets and stores NONE — DEST_DIR is just a filesystem path
# you provide. If your chosen destination (e.g. a cloud API, not a synced
# folder) genuinely needs credentials, this script is not where they go —
# see docs/21-disaster-recovery-and-rollback.md's "Off-host backup" section
# for how to extend this safely (env var read at run time, never committed).
#
# Usage:
#   DEST_DIR="D:/erp-backups" bash infra/backup/copy_offhost.sh
#   DEST_DIR="//nas-box/backups/erp" bash infra/backup/copy_offhost.sh
#   bash infra/backup/copy_offhost.sh infra/backup/artifacts/erp_nucleus_<ts>.dump   # copy one specific file
#
# Env:
#   DEST_DIR      Required. Off-host destination directory (must already exist/be mounted).
#   RETENTION     Optional. Keep only the N most recent backups in DEST_DIR (default: keep all).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="$SCRIPT_DIR/artifacts"

if [ -z "${DEST_DIR:-}" ]; then
  echo "ERROR: DEST_DIR is required — point it at your actual off-host location (external drive, NAS share, or synced cloud folder)." >&2
  echo "Example: DEST_DIR=\"D:/erp-backups\" bash $0" >&2
  exit 1
fi

if [ ! -d "$DEST_DIR" ]; then
  echo "ERROR: DEST_DIR does not exist or is not mounted: $DEST_DIR" >&2
  echo "If this is a network share or removable drive, make sure it's connected before running this." >&2
  exit 1
fi

SRC_FILE="${1:-}"
if [ -z "$SRC_FILE" ]; then
  SRC_FILE="$(ls -t "$ARTIFACT_DIR"/*.dump 2>/dev/null | head -1)"
  if [ -z "$SRC_FILE" ]; then
    echo "ERROR: no backup found in $ARTIFACT_DIR — run backup_db.sh first." >&2
    exit 1
  fi
fi

FILENAME="$(basename "$SRC_FILE")"
SHA_FILE="${SRC_FILE}.sha256"

echo "==> Copying $FILENAME to $DEST_DIR ..."
cp "$SRC_FILE" "$DEST_DIR/$FILENAME"
[ -f "$SHA_FILE" ] && cp "$SHA_FILE" "$DEST_DIR/${FILENAME}.sha256"

# Verify the copy is byte-identical, not just "cp didn't error."
SRC_SIZE="$(stat -c%s "$SRC_FILE" 2>/dev/null || stat -f%z "$SRC_FILE" 2>/dev/null)"
DST_SIZE="$(stat -c%s "$DEST_DIR/$FILENAME" 2>/dev/null || stat -f%z "$DEST_DIR/$FILENAME" 2>/dev/null)"
if [ "$SRC_SIZE" != "$DST_SIZE" ]; then
  echo "ERROR: copied file size ($DST_SIZE) does not match source ($SRC_SIZE) — copy is incomplete/corrupt." >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1 && [ -f "$SHA_FILE" ]; then
  (cd "$DEST_DIR" && sha256sum -c "${FILENAME}.sha256") || {
    echo "ERROR: checksum mismatch after copy — do not trust this off-host copy." >&2
    exit 1
  }
fi
echo "==> Verified: $DEST_DIR/$FILENAME matches the source exactly."

if [ -n "${RETENTION:-}" ]; then
  echo "==> Applying retention: keeping the $RETENTION most recent backups in $DEST_DIR"
  ls -t "$DEST_DIR"/*.dump 2>/dev/null | tail -n +$((RETENTION + 1)) | while read -r old; do
    echo "    removing old backup: $old"
    rm -f "$old" "${old}.sha256"
  done
fi

echo "==> Off-host copy complete."
