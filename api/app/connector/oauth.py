"""OAuth 2.1 authorization server for the Claude connector.

Claude (web, phone, desktop) connects to a remote MCP server with the
authorization-code flow + PKCE and registers itself first (RFC 7591). The
person approves on Lifey's own sign-in page, so the password is only ever typed
into Lifey. Everything stored is hashed; tokens are read-only ("lifey:read").
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError, RefreshToken, RegistrationError, TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .. import db

SCOPE = "lifey:read"
ACCESS_TTL = 60 * 60                 # 1 hour
REFRESH_TTL = 30 * 24 * 60 * 60      # 30 days, rotated on every use
CODE_TTL = 5 * 60
REQUEST_TTL = 10 * 60
DEFAULT_REDIRECT_HOSTS = ("claude.ai", "claude.com")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def public_url() -> str:
    return (os.environ.get("MCP_PUBLIC_URL") or os.environ.get("WEB_URL") or "http://localhost:8101").rstrip("/")


def enabled() -> bool:
    return os.environ.get("ENABLE_MCP", "").strip().lower() in ("1", "true", "yes", "on")


def allowed_redirect_hosts() -> tuple[str, ...]:
    raw = os.environ.get("MCP_REDIRECT_HOSTS")
    if raw:
        return tuple(h.strip().lower() for h in raw.split(",") if h.strip())
    return DEFAULT_REDIRECT_HOSTS


def redirect_allowed(uri: str) -> bool:
    """https callbacks on Claude's hosts, or a loopback address (desktop and CLI clients)."""
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host in allowed_redirect_hosts():
        return True
    return parsed.scheme == "http" and (host in LOCAL_HOSTS or f"[{host}]" in LOCAL_HOSTS)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> float:
    return time.time()


def redirect_with(uri: str, **params: str | None) -> str:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{uri}{'&' if '?' in uri else '?'}{query}"


# ---- storage (sync psycopg, called through a thread) --------------------------------------------

def _load_client(client_id: str) -> OAuthClientInformationFull | None:
    with db.connect() as conn:
        row = conn.execute("SELECT info FROM auth.oauth_clients WHERE client_id=%s", (client_id,)).fetchone()
    return OAuthClientInformationFull.model_validate(row[0]) if row else None


def _save_client(info: OAuthClientInformationFull) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO auth.oauth_clients (client_id, info) VALUES (%s, %s::jsonb)",
                     (info.client_id, info.model_dump_json()))
        conn.commit()


def _new_request(client_id: str, params: AuthorizationParams) -> str:
    request_id = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("DELETE FROM auth.oauth_requests WHERE expires_at < NOW()")
        conn.execute(
            "INSERT INTO auth.oauth_requests (id, client_id, params, expires_at) "
            "VALUES (%s, %s, %s::jsonb, NOW() + make_interval(secs => %s))",
            (request_id, client_id, params.model_dump_json(), REQUEST_TTL))
        conn.commit()
    return request_id


def load_request(request_id: str) -> tuple[OAuthClientInformationFull, AuthorizationParams] | None:
    if not request_id:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT client_id, params FROM auth.oauth_requests WHERE id=%s AND expires_at > NOW()",
                           (request_id,)).fetchone()
    if not row:
        return None
    client = _load_client(row[0])
    return (client, AuthorizationParams.model_validate(row[1])) if client else None


def discard_request(request_id: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM auth.oauth_requests WHERE id=%s", (request_id,))
        conn.commit()


def issue_code(request_id: str, client_id: str, params: AuthorizationParams, user_id: int) -> str:
    """Turn an approved request into a single-use authorization code."""
    code = secrets.token_urlsafe(32)
    data = AuthorizationCode(
        code="", scopes=params.scopes or [SCOPE], expires_at=_now() + CODE_TTL, client_id=client_id,
        code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly, resource=params.resource,
        subject=str(user_id))
    with db.connect() as conn:
        conn.execute("DELETE FROM auth.oauth_requests WHERE id=%s", (request_id,))
        conn.execute("DELETE FROM auth.oauth_codes WHERE expires_at < NOW()")
        conn.execute(
            "INSERT INTO auth.oauth_codes (code_hash, client_id, user_id, data, expires_at) "
            "VALUES (%s, %s, %s, %s::jsonb, NOW() + make_interval(secs => %s))",
            (_hash(code), client_id, user_id, data.model_dump_json(), CODE_TTL))
        conn.commit()
    return code


def _take_code(client_id: str, code: str) -> AuthorizationCode | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT data FROM auth.oauth_codes WHERE code_hash=%s AND client_id=%s AND expires_at > NOW()",
            (_hash(code), client_id)).fetchone()
    if not row:
        return None
    loaded = AuthorizationCode.model_validate(row[0])
    return loaded.model_copy(update={"code": code})


def _burn_code(code: str) -> bool:
    with db.connect() as conn:
        done = conn.execute("DELETE FROM auth.oauth_codes WHERE code_hash=%s", (_hash(code),)).rowcount
        conn.commit()
    return bool(done)


def _mint(client_id: str, user_id: int, scopes: list[str], resource: str | None) -> OAuthToken:
    access, refresh, pair = secrets.token_urlsafe(40), secrets.token_urlsafe(40), secrets.token_urlsafe(12)
    with db.connect() as conn:
        conn.execute("DELETE FROM auth.oauth_tokens WHERE expires_at < NOW()")
        for kind, value, ttl in (("access", access, ACCESS_TTL), ("refresh", refresh, REFRESH_TTL)):
            conn.execute(
                "INSERT INTO auth.oauth_tokens (token_hash, kind, client_id, user_id, scopes, resource, pair_id, "
                "expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW() + make_interval(secs => %s))",
                (_hash(value), kind, client_id, user_id, scopes, resource, pair, ttl))
        conn.commit()
    return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL,
                      refresh_token=refresh, scope=" ".join(scopes))


def _find_token(token: str, kind: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT client_id, user_id, scopes, resource, pair_id, EXTRACT(EPOCH FROM expires_at)::bigint "
            "FROM auth.oauth_tokens WHERE token_hash=%s AND kind=%s AND expires_at > NOW()",
            (_hash(token), kind)).fetchone()
    if not row:
        return None
    return {"client_id": row[0], "user_id": row[1], "scopes": list(row[2]), "resource": row[3],
            "pair_id": row[4], "expires_at": int(row[5])}


def _drop_pair(pair_id: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM auth.oauth_tokens WHERE pair_id=%s", (pair_id,))
        conn.commit()


def revoke_user(conn, user_id: int) -> int:
    """Sign out every connector for this person (used by "sign out everywhere")."""
    cur = conn.execute("DELETE FROM auth.oauth_tokens WHERE user_id=%s", (user_id,))
    conn.commit()
    return cur.rowcount


# ---- the provider -------------------------------------------------------------------------------

class LifeyProvider:
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await asyncio.to_thread(_load_client, client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or not all(redirect_allowed(u) for u in uris):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Redirect URIs must be on claude.ai / claude.com, or a loopback address.")
        await asyncio.to_thread(_save_client, client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not redirect_allowed(str(params.redirect_uri)):
            raise AuthorizeError("invalid_request", "Redirect URI is not allowed.")
        request_id = await asyncio.to_thread(_new_request, client.client_id, params)
        return f"{public_url()}/oauth/login?{urlencode({'request': request_id})}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str):
        return await asyncio.to_thread(_take_code, client.client_id, authorization_code)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        # Single use: if two exchanges race, only one of them can burn the code.
        if not await asyncio.to_thread(_burn_code, authorization_code.code):
            raise TokenError("invalid_grant", "Authorization code was already used.")
        return await asyncio.to_thread(
            _mint, client.client_id, int(authorization_code.subject or 0),
            authorization_code.scopes or [SCOPE], authorization_code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str):
        row = await asyncio.to_thread(_find_token, refresh_token, "refresh")
        if not row or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=row["scopes"],
                            expires_at=row["expires_at"], resource=row["resource"], subject=str(row["user_id"]))

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        row = await asyncio.to_thread(_find_token, refresh_token.token, "refresh")
        if not row:
            raise TokenError("invalid_grant", "Refresh token is no longer valid.")
        granted = scopes or refresh_token.scopes
        if not set(granted) <= set(refresh_token.scopes):
            raise TokenError("invalid_scope", "Cannot widen the scope on refresh.")
        await asyncio.to_thread(_drop_pair, row["pair_id"])     # rotate: the old pair stops working
        return await asyncio.to_thread(_mint, client.client_id, row["user_id"], granted, row["resource"])

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = await asyncio.to_thread(_find_token, token, "access")
        if not row:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=row["scopes"],
                           expires_at=row["expires_at"], resource=row["resource"], subject=str(row["user_id"]))

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        kind = "access" if isinstance(token, AccessToken) else "refresh"
        row = await asyncio.to_thread(_find_token, token.token, kind)
        if row:
            await asyncio.to_thread(_drop_pair, row["pair_id"])
