#!/usr/bin/env bash
# Weekly backup (Sundays), pushed off-box with rclone (Google Drive by default).
#
# NOT ENCRYPTED (owner's choice, 2026-10-19): anyone who can open the Drive folder can read it.
# Two files per run:
#   lifey_<date>.dump       Postgres dump (journal, health, habits, check-ins, ...)
#   lifey_files_<date>.tar  attached photos and PDFs
# .env and the Garmin login cache are deliberately NOT uploaded while backups are plaintext.
# On the 1st of the month the dump is also kept under monthly/ for a year.
# Older encrypted *.age files from before this change age out under the same retention.
#
# One-time setup on the VPS:
#   apt install rclone
#   rclone config create gdrive drive scope=drive.file
#   cat > /opt/lifey-ops/.backup.env <<ENV
#   RCLONE_REMOTE=gdrive:lifey-backups
#   ENV
#
# Restore: pg_restore -d lifey --no-owner lifey_<date>.dump
#
# Run by lifey-backup.timer. Every attempt is recorded in journal.backup_runs, which the web
# Settings page and the Telegram bot read. Exit status is non-zero on any failure.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.backup.env; set +a
: "${RCLONE_REMOTE:?RCLONE_REMOTE missing in .backup.env}"
KEEP_DAYS="${KEEP_DAYS:-45}"
DB_CONTAINER="${DB_CONTAINER:-lifey-db-1}"
API_CONTAINER="${API_CONTAINER:-lifey-api-1}"

umask 077
stamp="$(TZ=Asia/Phnom_Penh date +%Y-%m-%d)"
day_of_month="$(TZ=Asia/Phnom_Penh date +%d)"
work="$(mktemp -d)"
log="$work/rclone.log"
run_id=""
total=0
trap 'rm -rf "$work"' EXIT

psql_db() { docker exec -i "$DB_CONTAINER" psql -U lifey -d lifey -v ON_ERROR_STOP=1 -Atq "$@"; }

run_id="$(psql_db -c "INSERT INTO journal.backup_runs (destination) VALUES ('${RCLONE_REMOTE//\'/}') RETURNING id" 2>/dev/null || true)"

finish() {   # finish <ok|fail> <detail>
  local ok="$1" detail="${2:-}"
  [ -n "$run_id" ] || return 0
  local flag="false"; [ "$ok" = ok ] && flag="true"
  psql_db -v d="$detail" -v b="$total" <<SQL >/dev/null 2>&1 || true
UPDATE journal.backup_runs SET finished_at = NOW(), ok = ${flag}, bytes = :b,
       files = CASE WHEN ${flag} THEN 2 ELSE NULL END, detail = NULLIF(:'d', '') WHERE id = ${run_id};
SQL
}

fail() {
  local msg="$1"
  [ -s "$log" ] && msg="$msg: $(tail -c 400 "$log" | tr '\n' ' ')"
  echo "backup FAILED: $msg" >&2
  finish fail "$msg"
  exit 1
}

save_to() {      # save_to <outfile>   (stdin -> file, must be non-empty)
  cat > "$1" && [ -s "$1" ]
}

upload() {       # upload <local file> <remote name>
  local file="$1" name="$2" size
  size="$(stat -c %s "$file")"
  rclone copyto "$file" "${RCLONE_REMOTE}/${name}" 2>>"$log" || fail "upload of $name failed"
  # Drive can take a while to show a new file or its final size, so retry before giving up.
  local try seen=""
  for try in 1 2 3 4 5 6; do
    rclone lsjson "${RCLONE_REMOTE}/${name}" 2>>"$log" | grep -q "\"Size\":${size}[,}]" && { seen=1; break; }
    sleep $((try * 10))
  done
  [ -n "$seen" ] || fail "$name is not on the remote at the expected size"
  total=$((total + size))
}

# 1. database
docker exec "$DB_CONTAINER" pg_dump -U lifey -Fc lifey | save_to "$work/lifey_${stamp}.dump" \
  || fail "database dump failed"

# 2. attached files
docker exec "$API_CONTAINER" sh -c 'mkdir -p /data/attachments && tar -C /data/attachments -cf - .' \
  | save_to "$work/lifey_files_${stamp}.tar" || fail "attachments archive failed"

upload "$work/lifey_${stamp}.dump" "lifey_${stamp}.dump"
upload "$work/lifey_files_${stamp}.tar" "lifey_files_${stamp}.tar"

if [ "$day_of_month" = "01" ]; then
  rclone copyto "$work/lifey_${stamp}.dump" "${RCLONE_REMOTE}/monthly/lifey_${stamp}.dump" 2>>"$log" \
    || fail "monthly copy failed"
fi

# Retention: dailies for KEEP_DAYS, monthlies for a year. The *.age patterns clear the old encrypted files.
for pattern in "lifey_*.dump" "lifey_files_*.tar" "lifey_*.dump.age" "lifey_files_*.tar.age" "lifey_secrets_*.tar.age"; do
  rclone delete --min-age "${KEEP_DAYS}d" "${RCLONE_REMOTE}" --include "$pattern" --max-depth 1 2>>"$log" || true
done
rclone delete --min-age 365d "${RCLONE_REMOTE}/monthly" 2>>"$log" || true

finish ok ""
echo "backup ok: ${stamp} (${total} bytes, 2 files)"
