# CLAUDE.md: Lifey health intelligence

Read `SPEC.md` first. This file is the rule set. Place both files at the repo root after cloning
`github.com/davidboy49/lifey`.

## Who and how
- Owner is a developer (Next.js, NestJS, Postgres, Python basics) who wants to LEARN ML.
- **Split of work:** you build plumbing (schema, ingestion, jobs, agent tools, bot wiring, tests).
  The owner writes the ML in notebooks. For ML parts, scaffold empty notebooks with TODO cells and
  explain concepts; do not write the model, feature choices or interpretations for him.
- Build one phase at a time and confirm with him before the next.
- No new features until the current version has run 30 consecutive days.

## Stack and layout
- Python 3.12+, FastAPI, psycopg 3, Alembic, python-telegram-bot, pandas, LightGBM, SHAP.
  Web is Next.js (do not touch unless asked). No n8n. No NestJS. No agent frameworks.
- `api/app/health/` ingestion (existing). `api/app/ml/features.py` shared features.
  `api/app/ml/` jobs. `api/app/agent/` second bot and tools. `ml/notebooks/` owner's notebooks.
- Migrations in `api/migrations/versions/` (next number after 0004). Never edit applied migrations.
- Tests: `cd api && python -m pytest -q` against real Postgres (`TEST_DATABASE_URL`). No mocking the DB.

## Non-negotiable rules
1. ONE shared `features.py`, imported by both training notebooks and the nightly job. A parity test
   keeps them identical. No feature code anywhere else.
2. All dates normalized to `Asia/Phnom_Penh` (`app.health.quality.today()` / `HEALTH_TIMEZONE`).
   Sleep belongs to the wake-up date.
3. Explicit handling of missing days (watch not worn). NULL stays NULL; carry a missing flag and
   coverage; never silently fill. Any imputation is a named function and its output is flagged.
4. Model files are dated `<name>_YYYY-MM-DD.joblib`; keep the last 3.
5. Log every prediction next to its actual value (`ml.predictions`); weekly accuracy report vs the
   "tomorrow = today" baseline (and 7-day mean).
6. Monthly retrain; promote a new model only if it beats the current one on the last 30 days.
7. Security: Postgres never public; both bots locked to `TELEGRAM_CHAT_ID`; secrets only in `.env`
   (never committed, never printed); daily encrypted DB backup off-box with a restore drill.
8. Agent output: morning briefing <= 3 lines + exactly ONE action. Recovery mode auto-triggers
   after a detected crash night.
9. The agent never diagnoses. Symptoms, medication or anything clinical -> tell him to see a doctor.
10. Time-series evaluation only: expanding-window CV, no random splits, no leakage from the target
    day or derived Garmin scores into features for the metric they were computed from.

## Agent and message rules
- Plain text only: no emojis, no exclamation marks. Blunt coach tone, short.
- No generic advice ("sleep more", "drink water") unless backed by a number from his own data.
- Facts and numbers in messages come from computed rows or tool results, never from the model's memory.
  The LLM may phrase; it may not introduce a number it was not given.
- State data gaps in one line (not worn, sync failed, below coverage threshold) instead of guessing.
- One reminder at most per action; unanswered check-in is NULL, not "no".
- Journal free-text notes are never sent to the LLM. LLM sees derived daily numbers only.
- Tool limits: `query_db` is SELECT-only on `agent.*` views via role `lifey_agent` with timeout and
  row cap; `run_python` has no network and hard CPU/memory/time limits; writes only through fixed
  parameterised handlers (the Claude connector follows the same rule: see `connector/writes.py`). Per-message turn cap; daily and monthly (USD 5) spend ceilings, logged
  to `ml.llm_usage`.
- Paid LLM tier only (health data). Provider is DeepSeek, behind one adapter (OpenAI-compatible); never self-hosted.
  DeepSeek terms are weaker than Western providers, so send derived numbers only: no notes, raw payloads or identifiers.

## Constraints
- VPS: 2 GB RAM, shared with other services. Keep container `mem_limit`s; heavy jobs run as
  one-shot containers. TimesFM goes to production only if it wins AND fits; otherwise off-box.
- Existing Phase 1-2 code (sync, quality, readiness, anomaly, bot, web) is tested and live:
  extend, do not rewrite. Reuse `readiness.baseline` rather than adding a second baseline function.
- Do not touch the legacy bot's commands or the vidhealth bridge without asking.

## Decisions log
- 2026-10-10: Extend existing repo; no n8n; second bot for the agent; Python only.
- 2026-10-10: Primary target next-night sleep; HRV, RHR, Body Battery secondary.
- 2026-10-12: Baselines, mean7 and scored actuals exclude incomplete nights (single rule in features.incomplete_mask).
- 2026-10-11: Incomplete-recording guard: sleep < 3 h or BB high < 10 is never a crash night.
- 2026-10-11: Sleep target = 28-day mean 7.0 h (baseline 6.3 h). Briefing action closes the gap to it.
- 2026-10-10: Briefing 07:00, check-in 22:00, recovery mode automatic.
- 2026-10-10: Paid cheap LLM tier, DeepSeek chosen by owner; USD 5/month cap.
- 2026-10-10: One watch for the whole history; crash-night thresholds accepted as proposals.
- 2026-10-11: Crash night = HRV z<=-1.5 AND (sleep score or hours z<=-1.0), measured on real history (~3/month).
- 2026-10-10: Backups via rclone to a cloud drive, encrypted.
- 2026-10-15: Owner overrode the 30-day freeze for one feature: the learning thread (monthly focus, weekly recall, evidence shelf). Scope: skills of any kind (tech, life, sport, money, investing). Shelf is on demand via the Claude connector. Only topic and outcome leave the app, never notes or recall text.
- 2026-10-15: Claude connector may write, within fixed limits (owner chose silent logging, confirm-first for commitments). Separate scope `lifey:write`, granted only by ticking the capture box on the consent page. Allowed: log a learning session (undoable); propose a study, a monthly focus or a weekly quest into an inbox the owner accepts on the web. Never: close a focus, the review reflection or recall, journal notes, other habits, edit or delete. Every write is audited, rate-limited (60/hour), idempotent by request id, and listed in Settings with undo.

## Open items (resolve in Phase 1)
- Live row count and gap report for `health.daily_metrics`.
- Is the vidhealth bridge still the only Garmin client? Cut over or keep?
- Sleep-to-wake-date test.
