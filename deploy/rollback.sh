#!/usr/bin/env bash
# Hand the bot and the Garmin sync back to the old vidhealth stack.
# Anything logged through Lifey since the cutover stays in Lifey's database.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f /opt/lifey/compose.prod.yml)

echo "== stopping Lifey's bot and sync"
"${COMPOSE[@]}" --profile bot stop bot || true
systemctl disable --now lifey-sync.timer 2>&1 | grep -v "^Removed" || true

echo "== restoring the old stack"
systemctl enable --now garmin-sync.timer telegram-bot.service health-dashboard.service health-api.service health-mcp.service
systemctl enable --now lifey-follow.timer
sleep 3
for u in telegram-bot garmin-sync.timer health-dashboard health-api health-mcp lifey-follow.timer; do
  echo "$u: $(systemctl is-active "$u")"
done
