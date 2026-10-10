"""Health schema baseline

Revision ID: 0001
Revises:

Design notes (differences from vidhealth):
- Real DATE / TIMESTAMPTZ types instead of TEXT dates.
- The latest accepted payload per endpoint lives in endpoint_state, so a day
  can be re-merged without keeping a blob inside daily_metrics.
- Every distinct source payload is kept forever in source_payloads.
- Oxygen samples are only ever genuine timestamped readings, enforced by
  a CHECK constraint and a closed set of source types.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL = """
CREATE SCHEMA IF NOT EXISTS health;

CREATE TABLE health.daily_metrics (
    date                DATE PRIMARY KEY,
    hrv_last_night      INTEGER,
    hrv_weekly_avg      INTEGER,
    hrv_status          TEXT,
    sleep_score         INTEGER,
    sleep_duration      INTEGER,   -- seconds
    sleep_deep          INTEGER,
    sleep_light         INTEGER,
    sleep_rem           INTEGER,
    sleep_awake         INTEGER,
    resting_hr          INTEGER,
    min_hr              INTEGER,
    max_hr              INTEGER,
    bb_max              INTEGER,
    bb_min              INTEGER,
    bb_charged          INTEGER,
    bb_drained          INTEGER,
    stress_avg          INTEGER,
    stress_max          INTEGER,
    steps               INTEGER,
    floors              INTEGER,
    training_readiness  INTEGER,
    spo2_avg            DOUBLE PRECISION,
    spo2_min            DOUBLE PRECISION,
    respiration_avg     DOUBLE PRECISION,
    respiration_min     DOUBLE PRECISION,
    workout_type        TEXT,
    metric_sources      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- per metric: endpoint, path, status
    metric_issues       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- per metric: why a value was rejected
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Current accepted state of each Garmin endpoint for each day.
CREATE TABLE health.endpoint_state (
    date            DATE NOT NULL,
    endpoint        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN
        ('available','not_recorded','fetch_failed','parse_failed','stale','unavailable')),
    payload         JSONB,            -- NULL = never had one; '{}' = successfully empty
    fetched_at      TIMESTAMPTZ,
    attempted_at    TIMESTAMPTZ,
    payload_hash    TEXT,
    retained        BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (date, endpoint)
);

-- Immutable archive: every distinct payload ever received.
CREATE TABLE health.source_payloads (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date          DATE NOT NULL,
    endpoint      TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload       JSONB NOT NULL,
    UNIQUE (date, endpoint, payload_hash)
);

CREATE TABLE health.spo2_samples (
    date              DATE NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    value             DOUBLE PRECISION NOT NULL CHECK (value >= 1 AND value <= 100),
    respiration_rate  DOUBLE PRECISION,
    source            TEXT NOT NULL CHECK (source IN ('PULSE_OX','SLEEP')),
    PRIMARY KEY (date, ts)
);

CREATE TABLE health.spo2_processing (
    date              DATE PRIMARY KEY,
    algorithm_version TEXT NOT NULL,
    availability      TEXT NOT NULL,
    sample_count      INTEGER NOT NULL,
    rejected_samples  INTEGER NOT NULL DEFAULT 0,
    reason            TEXT NOT NULL,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE health.activities (
    activity_id               BIGINT PRIMARY KEY,
    date                      DATE NOT NULL,
    started_local             TIMESTAMP,  -- NULL when the source gave only a date
    name                      TEXT,
    type                      TEXT,
    duration_seconds          DOUBLE PRECISION,
    elapsed_duration_seconds  DOUBLE PRECISION,
    distance_meters           DOUBLE PRECISION,
    calories                  DOUBLE PRECISION,
    avg_hr                    DOUBLE PRECISION,
    max_hr                    DOUBLE PRECISION,
    aerobic_training_effect   DOUBLE PRECISION,
    anaerobic_training_effect DOUBLE PRECISION,
    avg_speed                 DOUBLE PRECISION,
    max_speed                 DOUBLE PRECISION,
    elevation_gain            DOUBLE PRECISION,
    steps                     INTEGER,
    raw                       JSONB NOT NULL
);
CREATE INDEX activities_date_idx ON health.activities (date);

CREATE TABLE health.sync_runs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL,
    details      JSONB
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP SCHEMA health CASCADE")
