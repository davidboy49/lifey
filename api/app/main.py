import asyncio
import logging
import os
import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from . import db, money
from .auth import deps as auth_deps
from .auth.routes import router as auth_router
from .demo import today_payload
from .health import read
from .models import Today

app = FastAPI(title="Lifey API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
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


@app.get("/api/health/sync", dependencies=protected)
def health_sync() -> dict:
    if not db.configured():
        return {"last_run": None}
    with db.connect() as conn:
        return {"last_run": read.last_sync(conn)}


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
