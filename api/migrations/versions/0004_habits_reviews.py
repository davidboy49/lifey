"""Custom habits and weekly reviews

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL = """
-- Habits the user adds beyond the built-in list. `tag` is what journal rows store.
CREATE TABLE journal.habits (
    tag         TEXT PRIMARY KEY CHECK (tag ~ '^[a-z0-9_]{1,48}$'),
    label       TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 48),
    unit        TEXT NOT NULL DEFAULT 'times' CHECK (length(unit) BETWEEN 1 AND 24),
    cue_if      TEXT,            -- "when ..." : the situation that triggers it
    cue_then    TEXT,            -- "I will ..." : what to do instead / next
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per ISO week (its Monday). The reflection is the user's own words.
CREATE TABLE journal.weekly_reviews (
    week_start  DATE PRIMARY KEY CHECK (EXTRACT(ISODOW FROM week_start) = 1),
    went_well   TEXT NOT NULL DEFAULT '',
    got_in_way  TEXT NOT NULL DEFAULT '',
    learned     TEXT NOT NULL DEFAULT '',
    plan_if     TEXT NOT NULL DEFAULT '',
    plan_then   TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE journal.weekly_reviews; DROP TABLE journal.habits;")
