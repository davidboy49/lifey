"""How you felt on waking

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL = """
-- 1 (awful) to 5 (great). NULL means not rated, never a neutral 3.
ALTER TABLE journal.checkins
    ADD COLUMN wake_feeling SMALLINT CHECK (wake_feeling IS NULL OR wake_feeling BETWEEN 1 AND 5);
"""


def upgrade() -> None:
    op.execute(SQL)
