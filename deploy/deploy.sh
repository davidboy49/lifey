#!/usr/bin/env bash
# Build and (re)start Lifey on the VPS. Idempotent; safe to re-run for updates.
#
#   git clone https://github.com/davidboy49/lifey /opt/lifey && /opt/lifey/deploy/deploy.sh
#
# The VPS is small and shared, so the web build runs under a hard memory cap:
# if it blows past it, only the build is killed, never your other services.
set -euo pipefail
cd "$(dirname "$0")/.."

# A build needs about 1.5 GB of scratch space for the API and web images. Starting one on a full
# disk fails halfway and leaves partial layers behind, so refuse up front. Override: MIN_FREE_GB=1
need_gb="${MIN_FREE_GB:-3}"
free_kb="$(df --output=avail -k / | tail -1 | tr -d ' ')"
if [ "$free_kb" -lt $((need_gb * 1024 * 1024)) ]; then
  echo "Not deploying: only $((free_kb / 1024 / 1024)) GB free on /, need ${need_gb} GB." >&2
  echo "Free space first (docker image prune -f, old backups, unused images), then re-run." >&2
  exit 1
fi

if [ ! -f .env ]; then
  umask 077
  pw="$(openssl rand -hex 24)"
  cat > .env <<EOF
POSTGRES_PASSWORD=${pw}
DATABASE_URL=postgresql://lifey:${pw}@db:5432/lifey
HEALTH_TIMEZONE=Asia/Phnom_Penh
ENABLE_BANK_IMPORT=0
APP_ORIGINS=https://lifey.fearlessonline.shop,http://localhost:8100
AUTH_COOKIE_SECURE=1
WEB_URL=https://lifey.fearlessonline.shop
ENABLE_MCP=1
EOF
  echo "created .env (secrets generated, not printed)"
fi

[ -d .git ] && git pull --ff-only

docker build -t lifey-api:latest api
docker build --memory=1g --memory-swap=1800m \
  --build-arg API_URL=http://api:8000 -t lifey-web:latest web

docker compose -f compose.prod.yml up -d
# The bot lives behind a profile, so `up -d` skips it: recreate it when it is already running.
if docker ps --format '{{.Names}}' | grep -q '^lifey-bot-1$'; then
  docker compose -f compose.prod.yml --profile bot up -d bot
fi
docker image prune -f > /dev/null
docker compose -f compose.prod.yml ps
