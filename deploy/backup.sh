#!/usr/bin/env bash
# Nightly encrypted backup, pushed off-box with rclone (Google Drive by default).
#
# Three files per night, each encrypted with age to the PUBLIC key (the private key
# never lives on the VPS; whoever holds it can decrypt, nobody else):
#   lifey_<date>.dump.age         Postgres dump (journal, health, habits, check-ins, ...)
#   lifey_files_<date>.tar.age    attached photos and PDFs
#   lifey_secrets_<date>.tar.age  .env and the Garmin login cache, so a rebuild is not a re-setup
# On the 1st of the month the dump is also kept under monthly/ for a year.
#
# One-time setup on the VPS:
#   apt install age rclone
#   age-keygen -o lifey-backup.key        # on a trusted machine; copy it OFF the box, note the "public key:" line
#   rclone config create lifeydrive drive scope=drive.file    # on a PC with a browser, then copy rclone.conf
#   cat > /opt/lifey-ops/.backup.env <<ENV
#   AGE_RECIPIENT=age1...                 # the public key
#   RCLONE_REMOTE=lifeydrive:lifey-backups
#   RCLONE_CONFIG=/opt/lifey-ops/rclone.conf
#   ENV
#
# Restore: age -d -i lifey-backup.key lifey_<date>.dump.age | pg_restore -d lifey --no-owner
#
# Run by lifey-backup.timer. Every attempt is recorded in journal.backup_runs, which the web
# Settings page and the Telegram bot read. Exit status is non-zero on any failure.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.backup.env; set +a
: "${AGE_RECIPIENT:?AGE_RECIPIENT missing in .backup.env}"
: "${RCLONE_REMOTE:?RCLONE_REMOTE missing in .backup.env}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_CONTAINER="${DB_CONTAINER:-lifey-db-1}"
API_CONTAINER="${API_CONTAINER:-lifey-api-1}"
LIFEY_DIR="${LIFEY_DIR:-/opt/lifey}"

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
       files = CASE WHEN ${flag} THEN 3 ELSE NULL END, detail = NULLIF(:'d', '') WHERE id = ${run_id};
SQL
}

fail() {
  local msg="$1"
  [ -s "$log" ] && msg="$msg: $(tail -c 400 "$log" | tr '\n' ' ')"
  echo "backup FAILED: $msg" >&2
  finish fail "$msg"
  exit 1
}

encrypt_to() {   # encrypt_to <outfile>   (stdin -> age)
  age -r "$AGE_RECIPIENT" -o "$1" && [ -s "$1" ]
}

upload() {       # upload <local file> <remote name>
  local file="$1" name="$2" size
  size="$(stat -c %s "$file")"
  rclone copyto "$file" "${RCLONE_REMOTE}/${name}" 2>>"$log" || fail "upload of $name failed"
  rclone lsjson "${RCLONE_REMOTE}/${name}" 2>>"$log" | grep -q "\"Size\":${size}[,}]" \
    || fail "$name is not on the remote at the expected size"
  total=$((total + size))
}

# 1. database
docker exec "$DB_CONTAINER" pg_dump -U lifey -Fc lifey | encrypt_to "$work/lifey_${stamp}.dump.age" \
  || fail "database dump or encryption failed"

# 2. attached files
docker exec "$API_CONTAINER" sh -c 'mkdir -p /data/attachments && tar -C /data/attachments -cf - .' \
  | encrypt_to "$work/lifey_files_${stamp}.tar.age" || fail "attachments archive failed"

# 3. secrets: .env and the Garmin login cache
mkdir -p "$work/secrets"
cp "$LIFEY_DIR/.env" "$work/secrets/.env" || fail "could not read $LIFEY_DIR/.env"
docker cp "$API_CONTAINER:/data/garmin_tokens" "$work/secrets/garmin_tokens" >/dev/null 2>&1 || true
tar -C "$work/secrets" -cf - . | encrypt_to "$work/lifey_secrets_${stamp}.tar.age" || fail "secrets archive failed"

upload "$work/lifey_${stamp}.dump.age" "lifey_${stamp}.dump.age"
upload "$work/lifey_files_${stamp}.tar.age" "lifey_files_${stamp}.tar.age"
upload "$work/lifey_secrets_${stamp}.tar.age" "lifey_secrets_${stamp}.tar.age"

if [ "$day_of_month" = "01" ]; then
  rclone copyto "$work/lifey_${stamp}.dump.age" "${RCLONE_REMOTE}/monthly/lifey_${stamp}.dump.age" 2>>"$log" \
    || fail "monthly copy failed"
fi

# Retention: dailies for KEEP_DAYS, monthlies for a year.
for pattern in "lifey_*.dump.age" "lifey_files_*.tar.age" "lifey_secrets_*.tar.age"; do
  rclone delete --min-age "${KEEP_DAYS}d" "${RCLONE_REMOTE}" --include "$pattern" --max-depth 1 2>>"$log" || true
done
rclone delete --min-age 365d "${RCLONE_REMOTE}/monthly" 2>>"$log" || true

finish ok ""
echo "backup ok: ${stamp} (${total} bytes, 3 files)"
