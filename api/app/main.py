import asyncio
import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

from . import money
from .demo import today_payload
from .models import Today

app = FastAPI(title="Lifey API", version="0.1.0")
MAX_UPLOAD = 10 * 1024 * 1024


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/today", response_model=Today)
def today() -> Today:
    return today_payload()


@app.get("/api/money/status")
def money_status() -> dict:
    return {"enabled": money.enabled()}


@app.post("/api/money/import")
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
