from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import db
from . import deps, security, service

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_AGE = int(service.SESSION_IDLE.total_seconds())


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(deps.COOKIE, token, max_age=MAX_AGE, httponly=True,
                        secure=deps.cookie_secure(), samesite="lax", path="/")


@router.post("/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    with db.connect() as conn:
        try:
            user_id = service.authenticate(conn, body.username, body.password)
        except service.Locked as locked:
            raise HTTPException(429, "Too many attempts. Try again later.",
                                headers={"Retry-After": str(locked.seconds)})
        if user_id is None:
            # One message for unknown user and wrong password.
            raise HTTPException(401, "Invalid username or password.")
        token = service.create_session(conn, user_id, deps.client_ip(request),
                                       request.headers.get("user-agent"))
    _set_cookie(response, token)
    return {"username": service.normalize(body.username)}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    with db.connect() as conn:
        service.revoke_session(conn, request.cookies.get(deps.COOKIE))
    response.delete_cookie(deps.COOKIE, path="/")


@router.get("/me")
def me(user: dict = Depends(deps.current_user)) -> dict:
    return {"username": user["username"]}


@router.post("/password")
def change_password(body: PasswordChange, user: dict = Depends(deps.current_user)) -> dict:
    if deps.auth_disabled():
        raise HTTPException(400, "Authentication is disabled.")
    with db.connect() as conn:
        # Re-verify through the same path, so wrong attempts here are throttled too.
        try:
            ok = service.authenticate(conn, user["username"], body.current)
        except service.Locked as locked:
            raise HTTPException(429, "Too many attempts. Try again later.",
                                headers={"Retry-After": str(locked.seconds)})
        if ok is None:
            raise HTTPException(401, "Current password is incorrect.")
        problem = security.password_problem(body.new)
        if problem:
            raise HTTPException(422, problem)
        service.set_password(conn, user["id"], body.new)
        ended = service.revoke_all(conn, user["id"], except_session=user["session_id"])
    return {"ok": True, "other_sessions_ended": ended}
