#!/usr/bin/env bash
# Nightly encrypted Postgres backup, pushed off-box with rclone.
#
# One-time setup on the VPS (the private key never lives on the VPS):
#   apt install age rclone
#   age-keygen -o ~/lifey-backup.key     # copy this file OFF the box; note the "public key:" line
#   rclone config                        # create a remote, e.g. "gdrive"
#   cat > /opt/lifey/.backup.env <<ENV
#   AGE_RECIPIENT=age1...                # the public key
#   RCLONE_REMOTE=gdrive:lifey-backups
#   ENV
#
# Run by lifey-backup.timer. Exit status is non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.backup.env; set +a
: "${AGE_RECIPIENT:?AGE_RECIPIENT missing in .backup.env}"
: "${RCLONE_REMOTE:?RCLONE_REMOTE missing in .backup.env}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_CONTAINER="${DB_CONTAINER:-lifey-db-1}"

umask 077
stamp="$(TZ=Asia/Phnom_Penh date +%Y-%m-%d)"
out="$(mktemp -d)/lifey_${stamp}.dump.age"
trap 'rm -rf "$(dirname "$out")"' EXIT

docker exec "$DB_CONTAINER" pg_dump -U lifey -Fc lifey | age -r "$AGE_RECIPIENT" -o "$out"
[ -s "$out" ] || { echo "backup is empty" >&2; exit 1; }

rclone copyto "$out" "${RCLONE_REMOTE}/lifey_${stamp}.dump.age"
rclone delete --min-age "${KEEP_DAYS}d" "${RCLONE_REMOTE}" --include "lifey_*.dump.age"
echo "backup ok: lifey_${stamp}.dump.age ($(stat -c %s "$out") bytes)"
