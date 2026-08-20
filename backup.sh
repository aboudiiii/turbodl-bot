#!/usr/bin/env bash
#
# TurboDL — SQLite database backup
#
# Creates a consistent backup of data/turbodl.db into backups/ using
# SQLite's online backup (.backup), so it is safe to run while the bot
# is live. Keeps the 30 most recent backups and locks them down (chmod 600).
#
# Usage:
#   ./backup.sh [cron-tag]        # run manually (cron-tag optional)
#
# deploy.sh installs this as a daily cron job (03:00 UTC).

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${APP_DIR}/backups"
DB_FILE="${APP_DIR}/data/turbodl.db"
KEEP="${KEEP:-30}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

if [ ! -f "${DB_FILE}" ]; then
    echo "!! Database not found at ${DB_FILE} — nothing to backup."
    exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/turbodl_${STAMP}.db"

echo "==> Backing up ${DB_FILE} -> ${DEST}"
sqlite3 "${DB_FILE}" ".backup '${DEST}'"
chmod 600 "${DEST}"

# Prune old backups, keep the newest ${KEEP}.
ls -1t "${BACKUP_DIR}"/turbodl_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f --

echo "==> Backup complete. (${KEEP} most recent kept)"
ls -1t "${BACKUP_DIR}"/turbodl_*.db 2>/dev/null | head -n 5 | sed 's/^/   /'