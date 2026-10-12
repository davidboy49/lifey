"""OAuth for the MCP connector

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQL = """
-- Clients that registered themselves (RFC 7591), e.g. Claude.
CREATE TABLE auth.oauth_clients (
    client_id   TEXT PRIMARY KEY,
    info        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- An authorize request waiting for the owner to sign in on Lifey's own page.
-- `id` is unguessable and single-use; it doubles as the form's CSRF token.
CREATE TABLE auth.oauth_requests (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL REFERENCES auth.oauth_clients(client_id) ON DELETE CASCADE,
    params      JSONB NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);

-- Only hashes of codes and tokens are stored; the plain value is shown once.
CREATE TABLE auth.oauth_codes (
    code_hash   TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL REFERENCES auth.oauth_clients(client_id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL,
    data        JSONB NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE auth.oauth_tokens (
    token_hash  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('access', 'refresh')),
    client_id   TEXT NOT NULL REFERENCES auth.oauth_clients(client_id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL,
    scopes      TEXT[] NOT NULL,
    resource    TEXT,
    pair_id     TEXT NOT NULL,           -- an access token and its refresh token share one
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX oauth_tokens_pair ON auth.oauth_tokens (pair_id);
CREATE INDEX oauth_tokens_user ON auth.oauth_tokens (user_id);
"""


def upgrade() -> None:
    op.execute(SQL)
