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

## Brand

The source logo is `brand/lifey-logo.png`. `python brand/make_assets.py` (needs Pillow) derives everything the web app uses: the in-page logo and mark (`web/public/brand/*.webp`), the install and home-screen icons (`web/public/icons`), and the favicon files in `web/app`. The outputs are committed, so the Docker build needs no image tooling. To change the logo, replace the source and re-run the script.

## Authentication

Lifey has its own login; nothing in `/api` is readable without a session (a test enumerates the OpenAPI schema to keep it that way).

- Argon2id password hashes, 12 character minimum, no public signup.
- Random session token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie. Only a SHA-256 of the token is stored. 14-day sliding expiry, 90-day absolute.
- Lockout after 5 failed attempts per username (15 minutes); one generic error for unknown user and wrong password.
- State-changing requests must carry an `Origin` from `APP_ORIGINS`.
- Changing a password ends all other sessions.

```bash
python -m app.auth.cli create-user david        # hidden password prompt
python -m app.auth.cli set-password david
python -m app.auth.cli logout-everywhere david
python -m app.auth.cli list
```

On the VPS: `docker compose -f compose.prod.yml exec api python -m app.auth.cli create-user david`.
`AUTH_DISABLED=1` exists only for the no-database demo; never set it on a server.

## Journal, habits and the weekly review

- **Journal** (`/journal`): a day-by-day timeline of habits, quit-tracker entries, check-ins, notes and training. Entries can be added for any day up to 400 days back, with the time they happened. An entry added on a later day is marked *recalled*. A day with nothing logged is unknown, never clean.
- **Habits** (`/habits`): a 2/5/12 week grid with three distinct cell states (logged, not logged, unknown), the quit card (days free in the last 30, best run; a slip is one day, not a reset to zero), mood and energy rows, and your own habits with an optional "if / then" cue.
- **Review** (`/review`): the week in numbers with the days behind each figure, your own notes, habit patterns only once there are 8 nights in each group, then a short reflection and one if-then change. The bot sends a Sunday 19:00 nudge (`WEEKLY_REVIEW_TIME`, `WEB_URL`).
- **Data** (`/data`): daily metrics, activities, journal, alerts and sync runs as tables with CSV export (formula-safe). Gaps are blank, never zero.
- **Sync now**: a button on Today and Journal; one sync at a time, with a per-source result.

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

### Bridge to the running vidhealth (temporary)

While the old sync, bot, dashboard and MCP server still depend on the old database, it stays the only Garmin client. `lifey-follow.timer` (every 30 minutes, `deploy/follow.sh`) replays the last 7 days of its source payloads into Lifey through a read-only session. Lifey does not contact Garmin while this bridge is in use. When the consumers have moved over, disable the old `garmin-sync.timer`, set `GARMIN_EMAIL`/`GARMIN_PASSWORD` in `.env`, run `docker compose -f compose.prod.yml run --rm sync` on a timer, and remove the follower.

### Bank statement import

The Money page and (later) the bot run the existing Sure importer from `/opt/sure_import`, mounted read-only into the API container. Sure deduplicates on each row's reference, so importing the same statement twice is safe. Needs `ENABLE_BANK_IMPORT=1`, `SURE_IMPORT_PYTHON=/usr/local/bin/python` and `SURE_IMPORT_SCRIPT` in `.env`; the compose file points `SURE_API_URL` at Sure's container on its own network.

### Importing vidhealth history

```bash
pip install -e ".[import]"
python -m app.health.import_vidhealth path/to/vidhealth.dump --dry-run
python -m app.health.import_vidhealth path/to/vidhealth.dump
```

Takes a `pg_dump -Fc` of the vidhealth database. Raw payloads are replayed through the same merge and parse rules as a live sync, with their original receipt times; days that only have a stored merged payload are stamped with that row's own sync time, never "now". vidhealth's derived oxygen tables are ignored, so synthetic `MODEL_EPOCH` rows never enter Lifey, and genuine samples are re-derived from the raw payloads. Safe to re-run. Journal, training and body-composition logs are not imported yet; ENT and quit tracking are dropped.

Not ported yet: desaturation events and hourly oxygen aggregates (exploratory analytics) and anomaly alerts.

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
