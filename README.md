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

## Status

Built: design system (light and dark), Today, Trends, Money import UI, readiness logic with tests, API, Dockerfiles, Compose.
Uses sample data (`source: "demo"`) until the Garmin ingestion is ported.

Next milestones:

1. Postgres schema and Alembic baseline; port the revisioned Garmin ingestion and data-integrity tests from vidhealth.
2. Worker container, sync run history, freshness on every figure.
3. Log (journal, training, body composition) and Experiments (declare a habit, compare against baseline with uncertainty).
4. Telegram bot on the API; encrypted backup container with a restore drill.
5. PWA install and offline last-day view; cut over from vidhealth.

Not yet verified: the Docker images and Compose stack have not been built (Docker is not installed on the authoring machine).
