"""Settings editable from the web (reminder times and switches)

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SQL = """
CREATE TABLE journal.settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def upgrade() -> None:
    op.execute(SQL)
