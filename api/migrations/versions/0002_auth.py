"""App-level authentication

Revision ID: 0002
Revises: 0001

Sessions store only a SHA-256 of the cookie token, so a database leak cannot be
replayed as live sessions. login_attempts backs the per-username lockout.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL = """
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE auth.users (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       TEXT NOT NULL CHECK (username = lower(username) AND length(username) BETWEEN 3 AND 64),
    password_hash  TEXT NOT NULL,
    disabled       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at  TIMESTAMPTZ,
    UNIQUE (username)
);

CREATE TABLE auth.sessions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash    BYTEA NOT NULL UNIQUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,   -- sliding idle expiry
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    ip            TEXT,
    user_agent    TEXT
);
CREATE INDEX sessions_user_idx ON auth.sessions (user_id);

CREATE TABLE auth.login_attempts (
    username          TEXT PRIMARY KEY,
    failures          INTEGER NOT NULL DEFAULT 0,
    first_failure_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_until      TIMESTAMPTZ
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP SCHEMA auth CASCADE")
