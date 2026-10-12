import asyncio
import logging
import os
import tempfile
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db, money
from .auth import deps as auth_deps
from .auth.routes import router as auth_router
from .demo import today_payload
from .health import read, sync as garmin_sync
from .data_routes import router as data_router
from .sleep_routes import router as sleep_router
from .journal.habit_routes import router as habits_router
from .journal.review_routes import router as review_router
from .journal.routes import router as journal_router
from .connector import oauth as connector_oauth
from .models import Today

# The Claude connector (remote MCP + OAuth) is opt-in: nothing extra is exposed unless ENABLE_MCP=1.
connector_app = None
if connector_oauth.enabled():
    from .connector.server import build as build_connector

    connector_app = build_connector()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if connector_app is None:
        yield
    else:
        async with connector_app.router.lifespan_context(connector_app):
            yield


app = FastAPI(title="Lifey API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
MAX_UPLOAD = 10 * 1024 * 1024

if auth_deps.auth_disabled():
    logging.getLogger("lifey.auth").warning("AUTH_DISABLED=1: every API route is open. Local demo only.")


@app.middleware("http")
async def require_same_origin(request: Request, call_next):
    """CSRF defence on top of SameSite=Lax: state-changing requests must come
    from one of our own origins."""
    if request.method in auth_deps.UNSAFE and request.url.path.startswith("/api/"):
        origin = (request.headers.get("origin") or "").rstrip("/")
        if origin not in auth_deps.allowed_origins():
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
    return await call_next(request)


app.include_router(auth_router)
app.include_router(journal_router)
app.include_router(habits_router)
app.include_router(review_router)
app.include_router(data_router)
app.include_router(sleep_router)
if connector_app is not None:
    from .connector.login import router as connector_login_router

    app.include_router(connector_login_router)
protected = [Depends(auth_deps.current_user)]


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/today", response_model=Today, dependencies=protected)
def today() -> Today:
    """Real data when the database has any, otherwise the labelled demo."""
    if db.configured():
        with db.connect() as conn:
            found = read.today_from_db(conn)
        if found is not None:
            return found
    return today_payload()


SYNC_STALE_AFTER_S = 15 * 60  # a "running" record older than this is a crashed run, not a live one


class SyncRequest(BaseModel):
    days: int = Field(default=3, ge=1, le=7)


@app.get("/api/health/sync", dependencies=protected)
def health_sync() -> dict:
    """Last run, whether one is in progress, and the state of each Garmin source today."""
    if not db.configured():
        return {"last_run": None, "running": False, "sources": []}
    with db.connect() as conn:
        last = read.last_sync(conn)
        running = bool(last and last["status"] == "running" and last["age_seconds"] < SYNC_STALE_AFTER_S)
        return {"last_run": last, "running": running, "sources": read.source_states(conn)}


@app.post("/api/health/sync", status_code=202, dependencies=protected)
def start_health_sync(body: SyncRequest = SyncRequest()) -> dict:
    """Start a sync in the background and return at once; poll GET for the outcome."""
    if not (os.environ.get("GARMIN_EMAIL") and os.environ.get("GARMIN_PASSWORD")):
        raise HTTPException(503, "Garmin credentials are not configured on this server.")
    with db.connect() as conn:
        free = conn.execute("SELECT pg_try_advisory_lock(%s)", (garmin_sync.SYNC_LOCK_KEY,)).fetchone()[0]
        if free:
            conn.execute("SELECT pg_advisory_unlock(%s)", (garmin_sync.SYNC_LOCK_KEY,))
    if not free:
        raise HTTPException(409, "A sync is already running.")

    def run() -> None:
        try:
            from .bot import syncer  # pulls in pandas for alert dispatch

            syncer.smart_sync(body.days)
        except Exception:  # the run is recorded as failed by run_sync; keep details out of the response
            logging.getLogger("lifey.sync").exception("manual sync failed")

    threading.Thread(target=run, name="manual-sync", daemon=True).start()
    return {"started": True, "days": body.days}


@app.get("/api/money/status", dependencies=protected)
def money_status() -> dict:
    return {"enabled": money.enabled()}


@app.post("/api/money/import", dependencies=protected)
async def money_import(file: UploadFile = File(...)) -> dict:
    if not money.enabled():
        raise HTTPException(409, "Bank statement import is turned off (set ENABLE_BANK_IMPORT=1 to enable).")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Upload an ABA statement exported as .xlsx.")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 10 MB.")
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        summary = await asyncio.to_thread(money.run_statement_import, path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if "error" in summary:
        raise HTTPException(502, summary["error"])
    return summary


# Last, so every route above wins: /mcp, /authorize, /token, /register and the .well-known documents.
if connector_app is not None:
    app.mount("/", connector_app)
