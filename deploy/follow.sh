#!/usr/bin/env bash
# Replays the last days of the live vidhealth database into Lifey (read-only on
# the old side). Runs from lifey-follow.timer. Secrets are read from the two
# .env files at run time and handed over via a private temp file.
set -euo pipefail
cd "$(dirname "$0")/.."
OLD_ENV="${OLD_ENV:-/root/garmin-health/.env}"
DAYS="${1:-7}"

tmp="$(mktemp)"; chmod 600 "$tmp"; trap 'rm -f "$tmp"' EXIT
old_url="$(grep -E '^DATABASE_URL=' "$OLD_ENV" | head -1 | cut -d= -f2-)"
lifey_pw="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)"
{
  echo "OLD_DATABASE_URL=${old_url}"
  echo "DATABASE_URL=postgresql://lifey:${lifey_pw}@127.0.0.1:5439/lifey"
  echo "HEALTH_TIMEZONE=Asia/Phnom_Penh"
} > "$tmp"

docker run --rm --network host --memory=300m --env-file "$tmp" lifey-api:latest \
  python -m app.health.follow_vidhealth --days "$DAYS"
