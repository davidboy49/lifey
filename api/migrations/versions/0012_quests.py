"""Weekly quests

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

SQL = """
-- One measurable goal per ISO week (its Monday). Progress is never stored: it is scored from the
-- journal and the watch data each time it is read, so a corrected entry corrects the score.
CREATE TABLE journal.quests (
    week_start  DATE PRIMARY KEY CHECK (EXTRACT(ISODOW FROM week_start) = 1),
    kind        TEXT NOT NULL CHECK (kind IN ('habit_free', 'sleep_hours', 'bed_before', 'training')),
    target      INTEGER NOT NULL CHECK (target BETWEEN 1 AND 7),
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE journal.quests;")
