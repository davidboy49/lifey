"""ML schema: personal-baseline flags and crash nights

Revision ID: 0005
Revises: 0004

Phase 2 is statistics only. A row records what was measured, the baseline it was
compared with and how many baseline days stood behind it, so a flag can always be
audited. `algorithm_version` lets a rule change without rewriting history.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SQL = """
CREATE SCHEMA IF NOT EXISTS ml;

CREATE TABLE ml.daily_flags (
    date               DATE NOT NULL,
    metric             TEXT NOT NULL,
    value              DOUBLE PRECISION,        -- NULL = no reading that day (never 0)
    baseline           DOUBLE PRECISION,
    sd                 DOUBLE PRECISION,
    z                  DOUBLE PRECISION,
    flag               TEXT NOT NULL CHECK (flag IN
        ('low','high','normal','no_data','insufficient_baseline')),
    baseline_days      INTEGER NOT NULL,
    algorithm_version  TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, metric, algorithm_version)
);

CREATE TABLE ml.crash_nights (
    date               DATE NOT NULL,
    crash              BOOLEAN NOT NULL,
    reasons            JSONB NOT NULL DEFAULT '[]'::jsonb,
    algorithm_version  TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, algorithm_version)
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP SCHEMA ml CASCADE")
