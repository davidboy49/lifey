# Lifey Health Intelligence: SPEC

Status: DRAFT for approval. Written 2026-10-10 from the interview plus a read of the existing repo
(github.com/davidboy49/lifey, branch main).

## 1. What this is

Lifey already exists as a Python/FastAPI + Next.js + Postgres system that ingests Garmin data and
has a Telegram bot. This project adds a **learning layer** on top of it:

> personal baselines -> anomaly flags -> day-ahead forecasts -> drivers -> an LLM agent over Telegram
> that gives a short morning briefing, one action per day, and answers ad-hoc questions.

The owner (a developer) writes the ML himself in notebooks to learn it. The assistant builds the
plumbing and scaffolds notebooks with TODOs; it does not solve the ML exercises.

## 2. Decisions from the interview

| Topic | Decision |
|---|---|
| Base | Extend the existing `lifey` repo. Phases 1-2 are mostly built; this work adds `ml`, `agent`, check-in. |
| Orchestration | **No n8n.** Existing python-telegram-bot `JobQueue` + systemd timers + one-shot containers. |
| Backend language | Python (matches repo). Web stays Next.js, untouched. |
| Code location | Clone `davidboy49/lifey` into this folder. ML in `api/app/ml/` (importable) and `ml/notebooks/`. |
| Bot | **Second bot** (new token, new module `app.agent`, own container). Old bot and its commands are untouched. Both locked to the owner's chat ID. |
| Device | One Garmin watch for the whole history (confirmed). No device-regime tagging. |
| Timezone | `Asia/Phnom_Penh` everywhere (`HEALTH_TIMEZONE`, already used by `quality.today()`). |
| Primary target | **Sleep (duration and score).** Secondary tracked: HRV overnight, resting HR, Body Battery morning high. |
| Improvement target | **Sleep: 28-day mean of 7.0 h** (set 2026-10-11 by owner; baseline then 6.3 h, SD about 2.3 h). HRV target still to be set. |
| Morning briefing | 07:00 Asia/Phnom_Penh fixed. Contains: last night's verdict, today's forecast, biggest driver, did-the-action streak. Max 3 lines + exactly ONE action. |
| Recovery mode | Auto-pushed after a detected crash night (definition in 6.3). |
| Manual inputs | Alcohol (yes/no + units); workout RPE, late meal, caffeine. Collected in the 10pm check-in. Existing `/log` and `/habit` remain. Not collected: symptom score, supplements. |
| LLM | **DeepSeek** paid API (OpenAI-compatible, function calling) behind a provider adapter, so it can be swapped. Budget cap USD 5/month with a daily ceiling and a spend log. Privacy: DeepSeek is operated from China and its terms allow using inputs to improve services, so the LLM sees only derived daily numbers (no journal notes, no raw payloads, no identifiers). Revisit if that is not acceptable. |
| VPS | 2 GB RAM, shared with other services. LightGBM nightly in a one-shot container. TimesFM only if it wins in the notebook AND fits memory; otherwise run off-box. |
| Backups | Daily encrypted `pg_dump`, pushed with rclone to a cloud drive, monthly restore drill. |
| Tone | Blunt coach. Plain text. No emojis or exclamation marks. No generic advice without a number from his own data. |
| Use pattern | Ad-hoc chat is the primary interaction; the briefing and check-in are the push channel. |

## 3. Current state (verified from the repo)

Already built and covering the original Phases 1-2:

- `health.daily_metrics`: one row per `DATE`; HRV, sleep (duration, stages, score), resting HR,
  Body Battery, stress, steps, training readiness, SpO2, respiration. `metric_sources` and
  `metric_issues` JSONB record provenance per metric.
- `health.endpoint_state` + `health.source_payloads`: per-endpoint status (`available`,
  `not_recorded`, `fetch_failed`, `parse_failed`, `stale`, `unavailable`) and an immutable raw archive.
- `python -m app.health.sync smart N | backfill N [--force]`, systemd timer 6x/day.
- Missing steps are NULL not 0; out-of-range sentinels are NULL with a reason.
- `readiness.py`: HRV/sleep/RHR z-scores vs trailing baseline (min 10 prior days).
- `bot/anomaly.py`: SpO2 and readiness rules, alerts de-duplicated in `journal.anomaly_alerts`.
- `journal.*`: activity_logs, body_comp, anomaly_alerts, action_plans, coaching_reports, habits, reviews.
- Auth, Caddy/nginx, compose with memory caps, Postgres on loopback only, CI against Postgres 18.

Not built, and the scope of this spec:

- Shared `features.py`; training/serving parity tests.
- `ml` schema: baselines, flags, predictions with actuals, model registry, weekly accuracy.
- Notebooks (baselines, LightGBM + SHAP, TimesFM comparison).
- Nightly job, monthly retrain with promotion gate, dated model files.
- Agent bot, tools, briefing, recovery mode, 10pm check-in, LLM spend log.
- Off-box backup and restore drill.

Known risks from the README, to be resolved in Phase 1:

- "Sync has not run against a live Garmin account" and "Docker images never built" may be stale.
- Lifey currently *follows* the legacy vidhealth DB through a 30-minute bridge and does not contact
  Garmin itself. Cutover state is unknown.
- Sleep-to-wake-date is not asserted by a test; it relies on how Garmin interprets `get_sleep_data(date)`.

## 4. Architecture

```
Garmin --(sync job, 6x/day)--> health.* (Postgres, loopback only)
                                   |
              api/app/ml/features.py   <-- the ONLY feature code (notebooks + nightly job)
                                   |
 nightly one-shot container (02:30): baselines -> flags -> forecasts -> ml.predictions
 actuals backfill (after each sync) -> ml.predictions.actual
 weekly: accuracy report vs naive; monthly: retrain + promotion gate
                                   |
          read-only role `lifey_agent` + views `agent.*`
                                   |
 app.agent (2nd bot, JobQueue): 07:00 briefing | recovery mode | 22:00 check-in | chat
        LLM tool loop: query_db, run_python, get_drivers, get_forecast
```

No model server. Batch predictions only. LLM is an external API, never self-hosted.
The agent analyses by calling tools, not by reading pasted summaries.

## 5. Data model (new migrations 0005+, Alembic)

All dates are `DATE` in Asia/Phnom_Penh. Sleep belongs to the wake-up date.

| Table | Purpose / key columns |
|---|---|
| `ml.daily_features` (view or table) | Output of `features.build()`; one row per date; carries `n_missing`, `coverage`. |
| `ml.daily_flags` | `date, metric, value, baseline, sd, z, flag, baseline_days, algorithm_version` |
| `ml.predictions` | `made_on, target_date, metric, horizon_days, model_name, model_version, y_hat, lo, hi, naive_pred, mean7_pred, actual NULL, actual_filled_at` |
| `ml.model_registry` | `model_name, model_version (YYYY-MM-DD), path, trained_through, cv_mae, last30_mae, naive_last30_mae, promoted_at, status` |
| `ml.accuracy_weekly` | `week_start, metric, model_name, n, mae, naive_mae, mean7_mae, skill (1 - mae/naive_mae)` |
| `ml.llm_usage` | `ts, purpose, model, input_tokens, output_tokens, cost_usd` |
| `journal.daily_actions` | `date PK, action_id, action_text, evidence JSONB, issued_at, did_it BOOL NULL, answered_at` |
| `journal.checkins` | `date PK, alcohol BOOL, alcohol_units, rpe, late_meal BOOL, caffeine_after_14 BOOL, answered_at` (NULL = unknown, never "no") |

Missing-day policy: a date with no sync keeps a NULL row; features carry an explicit `*_missing` flag
and `coverage`; no forward-fill or interpolation unless a named function does it and the output is
flagged `imputed=true`. A prediction is withheld when the window coverage is below the threshold in
`features.py` and the message says so.

## 6. Components

### 6.1 `api/app/ml/features.py` (single source of truth)
Pure functions over a DataFrame read from `health.daily_metrics` (+ `journal.checkins`). Lags,
rolling mean/SD (min_periods set), day-of-week, days-since, missing flags, targets shifted by
horizon. No I/O inside feature functions. Imported by notebooks and by the nightly job.
Parity test: the nightly job's feature row for date D equals the notebook's for D, on fixture data.

### 6.2 Baselines and flags (Phase 2, statistical, no ML)
Trailing 28-day mean and SD per metric excluding the evaluated day, minimum prior days enforced,
z-score, flag at |z| >= 1.5. Reuses `readiness.baseline`/`spread` where sensible; one implementation only.

### 6.3 Crash night
Rule `z28-v2`, tuned in Phase 2 on 92 trusted days of real history: last night's HRV is at least
1.5 SD below its 28-day baseline AND at least one sleep metric (score or hours) is at least 1.0 SD
below its own, with at least 14 prior baseline days. Candidate rules on the same data:

| Rule | Nights | Per month |
|---|---|---|
| any of HRV/score/hours <= -1.5 (original proposal) | 20 | ~6.5 |
| any of HRV/score/hours <= -2.0 | 12 | ~3.9 |
| **HRV <= -1.5 AND (score or hours <= -1.0)** (adopted) | 10 | ~3.3 |
| at least 2 of 3 <= -1.0 | 22 | ~7.2 |

Triggers recovery mode once per detected night, de-duplicated by date.

### 6.4 Forecasting (Phase 3)
Target: next-night sleep duration and score (horizon 1 day); secondary HRV 1-day. Candidates:
naive (tomorrow = today), 7-day mean, LightGBM with SHAP drivers, TimesFM 2.5 zero-shot. Evaluation:
expanding-window time-series CV; never random splits. Realistic note: 100-365 rows is small; expect
modest skill, keep features few, and report skill vs naive honestly. The nightly job runs whichever
candidate wins on the last 30 days.

### 6.5 Model lifecycle
Files `models/<name>_<YYYY-MM-DD>.joblib`, keep last 3. Monthly retrain; promote only if
`last30_mae` beats the current promoted model. Registry row written either way.

### 6.6 Agent
- `query_db(sql)`: SELECT only; role `lifey_agent`; views `agent.*`; `statement_timeout`; row cap.
  Journal free-text notes are excluded from the views.
- `run_python(code)`: subprocess, no network, CPU/memory/time limits, read-only DB role, pandas/numpy only.
- `get_forecast(metric, horizon)`: reads `ml.predictions` with interval and data coverage.
- `get_drivers(date, metric)`: reads precomputed SHAP/driver rows for that date.
- Writes happen only through fixed, parameterised handlers (`log_checkin`), never free SQL.
- Per-message turn cap and a daily USD ceiling; every call logged to `ml.llm_usage`.
- Clinical guardrail: anything about symptoms, medication, diagnosis -> no analysis, tell him to see a doctor.

### 6.7 Messages
- Briefing: <= 3 lines + exactly one `Action:` line. Facts come from computed rows; the LLM may
  phrase but not add numbers. If data is missing or stale it says so in one line.
- Recovery mode: sent after a detected crash night; states the number, the one action, no more.
- 22:00 check-in: "Did you do: <action>?" yes/no buttons, then alcohol / RPE / late meal / caffeine
  as quick buttons. One reminder maximum; unanswered = NULL.

### 6.8 Backups and security
Nightly `pg_dump -Fc` -> encrypt (age) -> rclone to cloud drive; keep 14 dailies; restore drill monthly
into a scratch DB. Secrets only in `.env`. Postgres bound to loopback (already). Agent bot rejects any
chat ID except `TELEGRAM_CHAT_ID`.

## 7. Phases (one at a time, confirm between each)

| # | Name | Work | Done when |
|---|---|---|---|
| 1 | Verify and close ingestion gaps (IN PROGRESS, see 13) | Clone repo, run tests, check live row count and gaps, add sleep-to-wake-date test, decide bridge vs direct Garmin, stand up backup | `daily_metrics` has >= 90 rows with coverage report; sync runs on schedule; backup restores |
| 2 | Baselines + anomalies (BUILT, see 14) | `features.py` v1, `ml.daily_flags`, crash-night rule, flags into briefing text (template, no LLM) | 7 consecutive days of correct flags; owner sets improvement target |
| 3 | ML notebooks | Scaffolds only (owner writes the ML); then nightly job, registry, accuracy report, retrain gate | Weekly accuracy report vs naive is produced for 2 weeks |
| 4 | Agent | Second bot, tools, briefing, recovery mode, 22:00 check-in, spend log | Chat answers via tools; 7 days of briefing + check-in without manual fixes |

Feature freeze: no new features until the current version has run 30 consecutive days.

## 8. Success metrics

- Reliability: briefing delivered by 07:05 on >= 95% of days; sync success rate; zero silent fills.
- Honesty: every prediction has a stored actual within 2 days of its target date.
- Model value: skill vs "tomorrow = today" over a rolling 30 days reported weekly; a model is
  promoted only if it beats the incumbent on the last 30 days.
- Behaviour: check-in answer rate and action-completion streak (reported, not nagged).
- Outcome: improvement target on the primary metric (value set after Phase 2).
- Cost: LLM spend <= USD 5/month; no daily ceiling breaches.

## 9. Non-negotiable rules
See `CLAUDE.md`. Copied there verbatim so they are loaded every session.

## 10. Out of scope
n8n, self-hosted LLMs, a model server, multi-user support, diagnosis of any kind, new Garmin metrics
before 30 stable days, rewriting the existing web app or bot.

## 11. Collaboration contract
- Assistant builds: migrations, ingestion fixes, `features.py` plumbing, jobs, tools, bot wiring, tests.
- Owner writes: baselines notebook, LightGBM, SHAP interpretation, TimesFM comparison.
- Assistant provides for ML: empty notebooks with TODO cells, data-loading cells, the evaluation
  harness contract, and explanations. It does not fill in the model/feature-selection answers.

## 12. Assumptions to confirm at approval
1. ~~One watch~~ Confirmed by owner.
2. Row count is 90-365, as you reported; I will verify against the live DB in Phase 1.
3. ~~LLM provider~~ DeepSeek (owner's choice); privacy limits above.
4. The primary target is next-night sleep; "Habits" is an input, not an outcome.
5. Crash-night thresholds in 6.3 are proposals, tuned on your data in Phase 2 (owner accepted).
6. Briefing at 07:00 uses data from the 06:05 sync; if sleep has not landed it says so.
7. 22:00 check-in time (you said 10pm); briefing contains the previous night's check-in streak.

## 13. Phase 1 log
- 2026-10-10: repo cloned into this folder; local venv at `api/.venv`; all 126 tests pass against embedded Postgres (`pgserver`).
- Added: sleep wake-date guard in `quality.parse_daily` + test; `app.ml.coverage` read-only report + tests;
  `deploy/backup.sh`, `deploy/restore-drill.sh`, `lifey-backup.{service,timer}` (written, NOT yet run on the VPS).
- Pending on the VPS (owner runs; needs live DB): coverage report, cutover/bridge decision, backup install.

## 14. Phase 2 log
- 2026-10-11: migration 0005 (`ml.daily_flags`, `ml.crash_nights`); `app/ml/features.py` (single feature
  source), `flags.py`, `briefing.py`; compose service `ml`; `lifey-briefing.{service,timer}` (timer NOT enabled:
  needs `AGENT_BOT_TOKEN`). 140 tests.
- Crash rule changed from the 6.3 proposal after measuring it on real data (see 6.3).
- Open: owner sets the improvement target from the baselines (needs his sign-off); 7 consecutive days of
  correct flags before Phase 3.
