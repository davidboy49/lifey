# Lifey

A calm personal app for health and money. It replaces the Streamlit-based `vidhealth` dashboard with a typed API and a mobile-first web app.

**Purpose:** answer "how is my body trending, what should I do today, and what has actually helped?" Every figure shows where it came from (measured, Garmin estimate, Garmin score, or not recorded). A missing reading is drawn as a gap, never as zero.

## Stack

| Part | Choice |
|---|---|
| `web/` | Next.js, React, Tailwind v4, installable PWA (planned) |
| `api/` | FastAPI, Pydantic v2 |
| Database | PostgreSQL 18, Alembic migrations (planned) |
| Jobs | Worker container for Garmin sync and coaching (planned) |
| Edge | Caddy, with Tailscale or Cloudflare Access in front |
| Packaging | Docker Compose |

## Modules

- **Health**: Today (readiness verdict with evidence), Trends (28 days against your own baseline).
- **Money**: ABA statement import. It runs the existing external Sure importer through an adapter (`api/app/money.py`), so it can be swapped for a native importer later. Its data stays separate from health data. Off unless `ENABLE_BANK_IMPORT=1`.

ENT and quit tracking from vidhealth are intentionally not carried over.

## Run it

```bash
# API
cd api && pip install -e ".[test]" && python -m pytest -q && uvicorn app.main:app --port 8000

# Web (second terminal)
cd web && npm install && npm run dev      # http://localhost:3000
```

Or the full stack: copy `.env.example` to `.env`, then `docker compose up --build` and open http://localhost:8080.

## Garmin ingestion

Ported from vidhealth with the same provenance rules (`api/app/health/`):

- Each endpoint is fetched independently. A failed endpoint keeps its last good value and is marked `fetch_failed`; a malformed one is `parse_failed`; a successful empty answer corrects old data.
- Every distinct payload is archived forever in `health.source_payloads`. The current accepted state per endpoint is `health.endpoint_state`.
- One transaction per day (daily metrics, oxygen samples, activities), serialised by an advisory lock. A sync lock prevents parallel runs.
- Oxygen: only genuine timestamped samples are stored; a database CHECK rejects values outside 1-100. Summary-only days create no samples.
- Missing steps are NULL, not 0; Garmin's own zeros are preserved. Out-of-range vendor sentinels become NULL with the reason recorded.
- Real `DATE` and `TIMESTAMPTZ` columns, schema `health`, migrations with Alembic (`api/migrations`).

```bash
cd api
alembic upgrade head                      # needs DATABASE_URL
python -m app.health.sync smart 3         # rolling three days
python -m app.health.sync backfill 30 --force
```

Exit status is non-zero for partial or failed runs. `GET /api/health/sync` returns the last run.

Not ported yet: desaturation events and hourly oxygen aggregates (exploratory analytics), the anomaly alerts, and importing vidhealth history. History can be rebuilt from vidhealth's `source_payloads` / `data/revisions` once you have a dump.

## Status

Built: design system (light and dark), Today, Trends, Money import UI, Garmin ingestion and Postgres schema, readiness logic, API, Dockerfiles, Compose, CI.
`/api/today` serves real data once the database has any; until then it serves labelled sample data (`source: "demo"`).

Next milestones:

1. ~~Postgres schema and Garmin ingestion~~ (done).
2. Scheduled sync (worker or n8n), history import from a vidhealth dump, desaturation events.
3. Log (journal, training, body composition) and Experiments (declare a habit, compare against baseline with uncertainty).
4. Telegram bot on the API; encrypted backup container with a restore drill.
5. PWA install and offline last-day view; cut over from vidhealth.

Verified: 27 API tests pass against a real PostgreSQL 16 (the code uses nothing 18-specific; CI uses 18). Not verified: the Docker images and Compose stack have never been built (Docker is not installed on the authoring machine), and the sync has not run against a live Garmin account.
