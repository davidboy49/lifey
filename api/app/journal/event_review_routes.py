"""Event reviews: create, list, view, edit and delete a look back on one event or day, with photos."""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import attachments
from ..attachment_routes import SERVE_HEADERS
from ..auth.deps import current_user
from . import event_reviews as ev

router = APIRouter(prefix="/api/event-reviews", tags=["event-reviews"], dependencies=[Depends(current_user)])


class ReviewIn(BaseModel):
    # Lengths and ranges are checked in event_reviews.validate, so the message names the field in plain words.
    date: str
    event: str
    mood: int | None = None
    energy: int | None = None
    notes: str = ""
    went_well: str = ""
    would_change: str = ""
    loop_tags: list[str] = []
    lesson: str = ""


def _clean(body: ReviewIn) -> dict:
    try:
        return ev.validate(body.model_dump())
    except ev.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_all(start: date | None = Query(default=None), end: date | None = Query(default=None),
             tag: str | None = Query(default=None)) -> dict:
    try:
        rows = ev.list_reviews(start, end, tag)
    except ev.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"reviews": rows, "tag_counts": ev.tag_counts(rows),
            "loop_tags": [{"tag": t, "label": ev.LOOP_LABELS[t]} for t in ev.LOOP_TAGS]}


@router.get("/lessons")
def lessons() -> dict:
    return {"lessons": ev.lessons()}


@router.get("/day/{day}")
def day(day: str) -> dict:
    try:
        return ev.day_data(ev.parse_day(day))
    except ev.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", status_code=201)
def create(body: ReviewIn) -> dict:
    return ev.create(_clean(body))


@router.get("/{review_id}")
def get_one(review_id: int) -> dict:
    found = ev.get(review_id)
    if not found:
        raise HTTPException(404, "That review doesn't exist.")
    return found


@router.put("/{review_id}")
def update(review_id: int, body: ReviewIn) -> dict:
    found = ev.update(review_id, _clean(body))
    if not found:
        raise HTTPException(404, "That review doesn't exist.")
    return found


@router.delete("/{review_id}", status_code=204)
def remove(review_id: int) -> None:
    if not ev.delete(review_id):
        raise HTTPException(404, "That review was already deleted.")


# ---------- photos ----------

@router.post("/{review_id}/photos", status_code=201)
async def add_photos(review_id: int, files: list[UploadFile] = File(...)) -> dict:
    if not ev.get(review_id):
        raise HTTPException(404, "That review doesn't exist.")
    saved, problems = [], []
    for upload in files[: ev.MAX_PHOTOS]:
        try:
            data = await upload.read(attachments.MAX_BYTES + 1)
            if len(data) > attachments.MAX_BYTES:
                raise attachments.Rejected(f"{upload.filename or 'That file'} is larger than 10 MB.")
            prepared = await asyncio.to_thread(ev.prepare_photo, data, upload.filename)
            saved.append(await asyncio.to_thread(ev.save_photo, review_id, prepared))
        except attachments.Rejected as exc:
            problems.append(str(exc))
    if not saved:
        raise HTTPException(422, problems[0] if problems else "Nothing could be added.")
    return {"photos": saved, "problems": problems}


def _serve(photo_id: int, thumb: bool) -> FileResponse:
    found = ev.get_photo(photo_id, thumb=thumb)
    if not found:
        raise HTTPException(404, "That photo isn't available.")
    path, mime, name = found
    safe = name.replace('"', "")
    return FileResponse(path, media_type=mime, headers={**SERVE_HEADERS, "Content-Disposition": f'inline; filename="{safe}"'})


@router.get("/photos/{photo_id}/thumb")
def photo_thumb(photo_id: int) -> FileResponse:
    return _serve(photo_id, thumb=True)


@router.get("/photos/{photo_id}")
def photo(photo_id: int) -> FileResponse:
    return _serve(photo_id, thumb=False)


@router.delete("/photos/{photo_id}", status_code=204)
def remove_photo(photo_id: int) -> None:
    if not ev.delete_photo(photo_id):
        raise HTTPException(404, "That photo was already removed.")
