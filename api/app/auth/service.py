"""Authentication state: users, sessions, lockout. All functions take a connection."""
from __future__ import annotations

from datetime import timedelta

from psycopg import Connection

from . import security

SESSION_IDLE = timedelta(days=14)
SESSION_ABSOLUTE = timedelta(days=90)
SEEN_RESOLUTION = timedelta(minutes=5)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_FOR = timedelta(minutes=15)


class Locked(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds


def normalize(username: str) -> str:
    return username.strip().lower()


def create_user(conn: Connection, username: str, password: str) -> int:
    username = normalize(username)
    problem = security.password_problem(password)
    if problem:
        raise ValueError(problem)
    row = conn.execute(
        "INSERT INTO auth.users (username, password_hash) VALUES (%s, %s) RETURNING id",
        (username, security.hash_password(password))).fetchone()
    conn.commit()
    return row[0]


def set_password(conn: Connection, user_id: int, password: str) -> None:
    problem = security.password_problem(password)
    if problem:
        raise ValueError(problem)
    conn.execute("UPDATE auth.users SET password_hash=%s WHERE id=%s",
                 (security.hash_password(password), user_id))
    conn.commit()


def _check_lock(conn: Connection, username: str) -> None:
    row = conn.execute(
        "SELECT EXTRACT(EPOCH FROM locked_until - NOW()) FROM auth.login_attempts "
        "WHERE username=%s AND locked_until > NOW()", (username,)).fetchone()
    if row:
        raise Locked(max(1, int(row[0])))


def _record_failure(conn: Connection, username: str) -> None:
    conn.execute(
        """INSERT INTO auth.login_attempts (username, failures, first_failure_at)
           VALUES (%s, 1, NOW())
           ON CONFLICT (username) DO UPDATE SET
             failures = CASE WHEN auth.login_attempts.first_failure_at < NOW() - %s
                             THEN 1 ELSE auth.login_attempts.failures + 1 END,
             first_failure_at = CASE WHEN auth.login_attempts.first_failure_at < NOW() - %s
                                     THEN NOW() ELSE auth.login_attempts.first_failure_at END""",
        (username, FAILURE_WINDOW, FAILURE_WINDOW))
    conn.execute(
        "UPDATE auth.login_attempts SET locked_until = NOW() + %s WHERE username=%s AND failures >= %s",
        (LOCK_FOR, username, MAX_FAILURES))
    conn.commit()


def authenticate(conn: Connection, username: str, password: str) -> int | None:
    """Return the user id on success, None on failure. Raises Locked when throttled."""
    username = normalize(username)
    _check_lock(conn, username)
    row = conn.execute(
        "SELECT id, password_hash FROM auth.users WHERE username=%s AND NOT disabled", (username,)).fetchone()
    ok = security.verify_password(row[1] if row else None, password)
    if not (ok and row):
        _record_failure(conn, username)
        return None
    conn.execute("DELETE FROM auth.login_attempts WHERE username=%s", (username,))
    conn.execute("UPDATE auth.users SET last_login_at=NOW() WHERE id=%s", (row[0],))
    if security.needs_rehash(row[1]):
        conn.execute("UPDATE auth.users SET password_hash=%s WHERE id=%s",
                     (security.hash_password(password), row[0]))
    conn.commit()
    return row[0]


def create_session(conn: Connection, user_id: int, ip: str | None, user_agent: str | None) -> str:
    token = security.new_token()
    conn.execute(
        """INSERT INTO auth.sessions (user_id, token_hash, expires_at, absolute_expires_at, ip, user_agent)
           VALUES (%s, %s, NOW() + %s, NOW() + %s, %s, %s)""",
        (user_id, security.token_hash(token), SESSION_IDLE, SESSION_ABSOLUTE, ip, (user_agent or "")[:300]))
    conn.commit()
    return token


def session_user(conn: Connection, token: str | None) -> dict | None:
    """The user for a valid session, sliding the idle expiry. None if invalid or expired."""
    if not token:
        return None
    row = conn.execute(
        """SELECT s.id, u.id, u.username, s.last_seen_at, s.absolute_expires_at
           FROM auth.sessions s JOIN auth.users u ON u.id = s.user_id
           WHERE s.token_hash = %s AND NOT u.disabled
             AND s.expires_at > NOW() AND s.absolute_expires_at > NOW()""",
        (security.token_hash(token),)).fetchone()
    if not row:
        return None
    session_id, user_id, username, last_seen, absolute = row
    seen_stale = conn.execute("SELECT %s < NOW() - %s", (last_seen, SEEN_RESOLUTION)).fetchone()[0]
    if seen_stale:
        conn.execute(
            "UPDATE auth.sessions SET last_seen_at=NOW(), expires_at=LEAST(NOW() + %s, %s) WHERE id=%s",
            (SESSION_IDLE, absolute, session_id))
        conn.commit()
    return {"id": user_id, "username": username, "session_id": session_id}


def revoke_session(conn: Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM auth.sessions WHERE token_hash=%s", (security.token_hash(token),))
        conn.commit()


def revoke_all(conn: Connection, user_id: int, except_session: int | None = None) -> int:
    cur = conn.execute("DELETE FROM auth.sessions WHERE user_id=%s AND id IS DISTINCT FROM %s",
                       (user_id, except_session))
    conn.execute("DELETE FROM auth.oauth_tokens WHERE user_id=%s", (user_id,))   # connectors too
    conn.commit()
    return cur.rowcount
