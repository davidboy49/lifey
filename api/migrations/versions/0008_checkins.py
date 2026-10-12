"""Evening check-in answers

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL = """
-- One row per day. NULL means "not answered", which is different from "no":
-- alcohol_units = 0 is a recorded dry day, NULL is unknown.
CREATE TABLE journal.checkins (
    date            DATE PRIMARY KEY,
    alcohol_units   NUMERIC CHECK (alcohol_units IS NULL OR alcohol_units BETWEEN 0 AND 30),
    late_caffeine   BOOLEAN,
    late_meal       BOOLEAN,
    rpe             SMALLINT CHECK (rpe IS NULL OR rpe BETWEEN 0 AND 10),   -- 0 = no workout
    answered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def upgrade() -> None:
    op.execute(SQL)
