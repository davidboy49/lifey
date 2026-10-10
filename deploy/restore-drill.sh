#!/usr/bin/env bash
# Monthly restore drill: prove a backup restores, without touching the live database.
#
#   deploy/restore-drill.sh <lifey_YYYY-MM-DD.dump.age> <path-to-age-private-key>
#
# Copy the private key to the box only for the drill and delete it afterwards.
set -euo pipefail
file="${1:?backup file}"; key="${2:?age private key}"
DB_CONTAINER="${DB_CONTAINER:-lifey-db-1}"
scratch="lifey_restore_drill"

docker exec "$DB_CONTAINER" psql -U lifey -d postgres -qc "DROP DATABASE IF EXISTS ${scratch}"
docker exec "$DB_CONTAINER" psql -U lifey -d postgres -qc "CREATE DATABASE ${scratch}"
age -d -i "$key" "$file" | docker exec -i "$DB_CONTAINER" pg_restore -U lifey -d "$scratch" --no-owner
rows="$(docker exec "$DB_CONTAINER" psql -U lifey -d "$scratch" -Atc 'SELECT count(*), max(date) FROM health.daily_metrics')"
docker exec "$DB_CONTAINER" psql -U lifey -d postgres -qc "DROP DATABASE ${scratch}"
echo "restore ok: daily_metrics (rows|latest date) = ${rows}"
