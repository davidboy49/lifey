"""Connector writes: audit trail and proposals waiting for approval

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SQL = """
-- Every write the Claude connector made or was refused. `ref_*` points at what it created, so a
-- logged session can be undone. Arguments are kept as sent; they never include journal notes.
CREATE TABLE journal.connector_audit (
    id               BIGSERIAL PRIMARY KEY,
    at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_id        TEXT,
    tool             TEXT NOT NULL,
    summary          TEXT NOT NULL CHECK (length(summary) <= 300),
    args             JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome          TEXT NOT NULL CHECK (outcome IN ('ok', 'refused')),
    ref_kind         TEXT CHECK (ref_kind IN ('activity_log', 'proposal')),
    ref_id           BIGINT,
    idempotency_key  TEXT CHECK (length(idempotency_key) <= 80),
    undone_at        TIMESTAMPTZ
);
CREATE INDEX connector_audit_at ON journal.connector_audit (at DESC);
-- The same request id for the same tool is the same write, not a second one.
CREATE UNIQUE INDEX connector_audit_idem ON journal.connector_audit (tool, idempotency_key)
    WHERE idempotency_key IS NOT NULL AND outcome = 'ok';

-- Things Claude suggests that change what you committed to. Nothing here takes effect until you accept.
CREATE TABLE journal.proposals (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('study', 'focus', 'quest')),
    payload     JSONB NOT NULL,
    why         TEXT NOT NULL DEFAULT '' CHECK (length(why) <= 300),
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at  TIMESTAMPTZ,
    CHECK ((status = 'pending') = (decided_at IS NULL))
);
CREATE INDEX proposals_pending ON journal.proposals (created_at) WHERE status = 'pending';
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE journal.proposals; DROP TABLE journal.connector_audit;")
