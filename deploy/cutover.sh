#!/usr/bin/env bash
# Move the Garmin sync and the Telegram bot from vidhealth to Lifey.
# Reversible with deploy/rollback.sh. Secrets are copied between the two .env
# files on this machine and never printed.
set -euo pipefail
cd "$(dirname "$0")/.."
OLD=/root/garmin-health
OLD_ENV="$OLD/.env"
COMPOSE=(docker compose -f /opt/lifey/compose.prod.yml)
OLD_UNITS=(telegram-bot.service garmin-sync.timer garmin-sync.service health-dashboard.service health-api.service health-mcp.service)

say() { printf '\n== %s\n' "$*"; }
need() { grep -qE "^$1=.+" "$OLD_ENV" || { echo "missing $1 in $OLD_ENV"; exit 1; }; }
getv() { grep -E "^$1=" "$OLD_ENV" | head -1 | cut -d= -f2-; }
setv() { # setv KEY VALUE  -> write into Lifey .env without echoing the value
  local k="$1" v="$2"
  grep -v "^${k}=" .env > .env.tmp || true
  printf '%s=%s\n' "$k" "$v" >> .env.tmp
  chmod 600 .env.tmp && mv .env.tmp .env
}

say "1. preflight"
for k in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID GARMIN_EMAIL GARMIN_PASSWORD; do need "$k"; done
docker image inspect lifey-api:latest >/dev/null
"${COMPOSE[@]}" exec -T db psql -U lifey -d lifey -Atc "select count(*) from journal.activity_logs" >/dev/null
echo "images and schema present"

say "2. copy credentials into Lifey's .env (values not shown)"
for k in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID GARMIN_EMAIL GARMIN_PASSWORD; do setv "$k" "$(getv "$k")"; done
setv ENABLE_BANK_IMPORT 1
setv HEALTH_TIMEZONE Asia/Phnom_Penh

say "3. copy the Garmin login cache so no fresh login is needed"
if [ -d "$OLD/.garmin_tokens" ]; then
  docker run --rm -u root -v lifey_garmin:/data -v "$OLD/.garmin_tokens":/src:ro lifey-api:latest \
    sh -c 'mkdir -p /data/garmin_tokens && cp -a /src/. /data/garmin_tokens/ && chown -R lifey /data'
  echo "token cache copied"
else
  echo "no token cache found; the first sync will log in normally"
fi

# From here on the old stack is down: any failure puts it back.
trap 'echo; echo "!! cutover failed - rolling back"; bash /opt/lifey/deploy/rollback.sh' ERR

say "4. stop the old stack (disabled so it stays off after a reboot)"
systemctl disable --now "${OLD_UNITS[@]}" 2>&1 | grep -v "^Removed" || true
systemctl disable --now lifey-follow.timer 2>&1 | grep -v "^Removed" || true

say "5. last catch-up from the old database (read-only)"
bash deploy/follow.sh 7

say "6. start the Lifey bot (same token) and the sync timer"
"${COMPOSE[@]}" --profile bot up -d bot
cp deploy/systemd/lifey-sync.service deploy/systemd/lifey-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now lifey-sync.timer

say "7. verify"
sleep 8
"${COMPOSE[@]}" ps bot --format '{{.Name}} {{.Status}}'
echo "-- Telegram accepts the token:"
"${COMPOSE[@]}" exec -T bot python -c "
import json, os, urllib.request
url = 'https://api.telegram.org/bot' + os.environ['TELEGRAM_BOT_TOKEN'] + '/getMe'
me = json.load(urllib.request.urlopen(url, timeout=15))
assert me.get('ok'), 'getMe failed'
print('bot account: @' + me['result']['username'])
"
"${COMPOSE[@]}" logs --no-log-prefix --tail 6 bot 2>&1 | sed -E 's#(bot)[0-9]+:[A-Za-z0-9_-]+#\1<token>#g' | cut -c1-160
echo "-- one sync run:"
"${COMPOSE[@]}" run --rm sync smart 1 2>&1 | tail -3 | cut -c1-300
systemctl list-timers lifey-sync.timer --no-legend | cut -c1-110
echo; echo "Cutover complete. Undo with: /opt/lifey/deploy/rollback.sh"
