"""FastAPI wiring: the session dependency and the origin check."""
from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Request

from .. import db
from . import service

COOKIE = "lifey_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
log = logging.getLogger("lifey.auth")


def auth_disabled() -> bool:
    return os.environ.get("AUTH_DISABLED") == "1"


def cookie_secure() -> bool:
    return os.environ.get("AUTH_COOKIE_SECURE", "1") != "0"


def allowed_origins() -> set[str]:
    raw = os.environ.get("APP_ORIGINS", "http://localhost:3000,http://localhost:8100")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def current_user(request: Request) -> dict:
    """Require a valid session. With AUTH_DISABLED=1 (local demo only) allow anyone."""
    if auth_disabled():
        return {"id": 0, "username": "anonymous", "session_id": None}
    if not db.configured():
        raise HTTPException(503, "Authentication needs the database.")
    token = request.cookies.get(COOKIE)
    with db.connect() as conn:
        user = service.session_user(conn, token)
    if not user:
        raise HTTPException(401, "Sign in required.")
    return user
