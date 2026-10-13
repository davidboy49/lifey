"""Attachments: add photos and PDFs to the journal, and fetch them back (logged in only)."""
from __future__ import annotations

import asyncio
import datetime as dt
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import attachments, backup_status
from .auth.deps import current_user
from .bot import store
from .health import quality
from .journal.routes import MAX_BACKDATE_DAYS

router = APIRouter(prefix="/api/attachments", tags=["attachments"], dependencies=[Depends(current_user)])

SERVE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, max-age=3600",
    "Referrer-Policy": "no-referrer",
}


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read(attachments.MAX_BYTES + 1)
    if len(data) > attachments.MAX_BYTES:
        raise attachments.Rejected(f"{upload.filename or 'That file'} is larger than 10 MB.")
    return data


async def _attach(log_id: int, files: list[UploadFile]) -> tuple[list[dict], list[str]]:
    saved, problems = [], []
    for upload in files:
        try:
            data = await _read(upload)
            saved.append(await asyncio.to_thread(attachments.add, log_id, data, upload.filename))
        except attachments.Rejected as exc:
            problems.append(str(exc))
    return saved, problems


@router.post("", status_code=201)
async def new_entry_with_files(files: list[UploadFile] = File(...), note: str = Form(""),
                               date: str | None = Form(None), time: str | None = Form(None)) -> dict:
    """Create a note entry carrying the files. The note may be empty when there is a file."""
    now = datetime.now(quality.user_timezone())
    today = now.date()
    try:
        day = dt.date.fromisoformat(date) if date else today
    except ValueError as exc:
        raise HTTPException(422, "Use a date like 2026-10-13.") from exc
    if day > today:
        raise HTTPException(422, "That date is in the future.")
    if (today - day).days > MAX_BACKDATE_DAYS:
        raise HTTPException(422, f"Entries can go back at most {MAX_BACKDATE_DAYS} days.")
    if time:
        try:
            datetime.strptime(time, "%H:%M")
        except ValueError as exc:
            raise HTTPException(422, "time must be HH:MM") from exc
    occurred = time or now.strftime("%H:%M")
    if day == today and time and time > now.strftime("%H:%M"):
        raise HTTPException(422, "That time is still in the future.")
    note = note.strip()[:2000]
    if not files:
        raise HTTPException(422, "Choose a file.")

    # Validate every file before creating the entry, so a rejected file never leaves an empty note behind.
    prepared, problems = [], []
    for upload in files[: attachments.MAX_PER_ENTRY]:
        try:
            prepared.append((await asyncio.to_thread(attachments.prepare, await _read(upload), upload.filename)))
        except attachments.Rejected as exc:
            problems.append(str(exc))
    if not prepared:
        raise HTTPException(422, problems[0] if problems else "Nothing could be attached.")

    log_id = store.log_activity(date_str=day.isoformat(), category="free_note", tag="note", note=note,
                                value=None, occurred_at=occurred)
    saved = []
    for item in prepared:
        try:
            saved.append(await asyncio.to_thread(attachments.save, log_id, item))
        except attachments.Rejected as exc:
            problems.append(str(exc))
    if not saved:
        store.delete_activity_log(log_id)
        raise HTTPException(422, problems[0] if problems else "Nothing could be attached.")
    return {"ids": [log_id], "date": day.isoformat(), "time": occurred, "recalled": day < today,
            "attachments": saved, "problems": problems}


@router.post("/{log_id}", status_code=201)
async def add_to_entry(log_id: int, files: list[UploadFile] = File(...)) -> dict:
    saved, problems = await _attach(log_id, files)
    if not saved:
        raise HTTPException(422, problems[0] if problems else "Nothing could be attached.")
    return {"attachments": saved, "problems": problems}


def _serve(attachment_id: int, thumb: bool, download: bool) -> FileResponse:
    found = attachments.get(attachment_id, thumb=thumb)
    if not found:
        raise HTTPException(404, "That file isn't available.")
    path, mime, name = found
    disposition = "attachment" if download else "inline"
    safe = name.replace('"', "")
    return FileResponse(path, media_type=mime, headers={
        **SERVE_HEADERS, "Content-Disposition": f'{disposition}; filename="{safe}"'})


@router.get("/{attachment_id}/thumb")
def thumbnail(attachment_id: int) -> FileResponse:
    return _serve(attachment_id, thumb=True, download=False)


@router.get("/{attachment_id}")
def download(attachment_id: int) -> FileResponse:
    found = attachments.get(attachment_id)
    is_pdf = bool(found and found[1] == attachments.PDF_MIME)
    return _serve(attachment_id, thumb=False, download=is_pdf)


@router.delete("/{attachment_id}", status_code=204)
def remove(attachment_id: int) -> None:
    if not attachments.delete(attachment_id):
        raise HTTPException(404, "That file was already removed.")
