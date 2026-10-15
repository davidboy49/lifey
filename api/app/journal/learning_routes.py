"""The learning thread: this month's focus, closing it, and the evidence shelf."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.deps import current_user
from ..bot import store
from ..health import quality
from . import learning, repo

router = APIRouter(prefix="/api/learning", tags=["learning"], dependencies=[Depends(current_user)])


class FocusBody(BaseModel):
    topic: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=24)
    outcome: str = Field(default="", max_length=600)
    plan_if: str = Field(default="", max_length=600)
    plan_then: str = Field(default="", max_length=600)
    why: str = Field(default="", max_length=600)


class FocusPatch(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=24)
    outcome: str | None = Field(default=None, max_length=600)
    plan_if: str | None = Field(default=None, max_length=600)
    plan_then: str | None = Field(default=None, max_length=600)
    why: str | None = Field(default=None, max_length=600)


class CloseBody(BaseModel):
    result: str = Field(max_length=16)
    next_step: str = Field(max_length=16)
    next_outcome: str = Field(default="", max_length=600)     # required when continuing
    plan_if: str | None = Field(default=None, max_length=600)
    plan_then: str | None = Field(default=None, max_length=600)


class StudyBody(BaseModel):
    citation: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=500)
    finding: str = Field(min_length=1, max_length=400)
    topic: str | None = Field(default=None, max_length=80)     # defaults to the active focus


def _valid(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def read() -> dict:
    today = quality.today()
    logs = store.get_activity_logs_between(learning.month_start(today).isoformat(), today.isoformat())
    return learning.overview(today, logs)


@router.put("/focus", status_code=201)
def set_focus(body: FocusBody) -> dict:
    """Start the focus for this month. Only one can be active: close the current one first."""
    clean = _valid(learning.validate_focus, body.model_dump())
    clean["habit_tag"] = learning.ensure_habit()
    created = repo.create_focus(learning.month_start(quality.today()), clean)
    if created is None:
        raise HTTPException(409, "You already have a focus. Close it before starting another.")
    return created


@router.patch("/focus/{focus_id}")
def edit_focus(focus_id: int, body: FocusPatch) -> dict:
    fields = _valid(learning.validate_focus, body.model_dump(exclude_unset=True, exclude_none=True), partial=True)
    if not fields:
        raise HTTPException(422, "Nothing to change.")
    if not repo.update_focus(focus_id, fields):
        raise HTTPException(404, "No active focus with that id.")
    return {"saved": True}


@router.post("/focus/{focus_id}/close")
def close_focus(focus_id: int, body: CloseBody) -> dict:
    """Mark the month met, partly or not met, then continue, switch or pause."""
    if body.result not in learning.RESULTS:
        raise HTTPException(422, "Say whether it was met, partly met or not met.")
    if body.next_step not in learning.NEXT_STEPS:
        raise HTTPException(422, "Pick continue, switch or pause.")
    focus = repo.get_focus(focus_id)
    if focus is None or focus["status"] != "active":
        raise HTTPException(404, "No active focus with that id.")
    carry = None
    if body.next_step == "continue":
        # A continued topic still needs a fresh outcome: the month is a new checkable commitment.
        carry = _valid(learning.validate_focus, {
            "topic": focus["topic"], "category": focus["category"], "outcome": body.next_outcome,
            "plan_if": focus["plan_if"] if body.plan_if is None else body.plan_if,
            "plan_then": focus["plan_then"] if body.plan_then is None else body.plan_then,
            "why": focus["why"]})
        carry["habit_tag"] = focus["habit_tag"]
    if not repo.close_focus(focus_id, body.result, body.next_step):
        raise HTTPException(404, "No active focus with that id.")
    renewed = repo.create_focus(learning.month_start(quality.today()), carry) if carry else None
    return {"closed": True, "next": renewed}


@router.post("/studies", status_code=201)
def pin_study(body: StudyBody) -> dict:
    """Keep a study for a topic. It is stored with its link and today's date, as the person supplied it."""
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "The link must start with http:// or https://")
    if body.topic and body.topic.strip():
        key = learning.topic_key(body.topic)
    else:
        active = repo.active_focus()
        if active is None:
            raise HTTPException(422, "Set a focus first, or say which topic this study is for.")
        key = active["topic_key"]
    new_id = repo.add_study(key, " ".join(body.citation.split()), url, " ".join(body.finding.split()),
                            quality.today())
    if new_id is None:
        raise HTTPException(409, "That link is already on this topic's shelf.")
    return {"id": new_id, "topic_key": key}


@router.delete("/studies/{study_id}", status_code=204)
def unpin_study(study_id: int) -> None:
    if not repo.delete_study(study_id):
        raise HTTPException(404, "No such study.")
