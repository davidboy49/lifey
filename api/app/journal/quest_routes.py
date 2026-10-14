"""The weekly quest: read this week's (or next week's), set it, clear it."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.deps import current_user
from ..health import quality
from . import quests, repo

router = APIRouter(prefix="/api/quest", tags=["quest"], dependencies=[Depends(current_user)])


class QuestBody(BaseModel):
    kind: str = Field(max_length=24)
    target: int = Field(ge=1, le=7)
    params: dict = Field(default_factory=dict)


def _editable_week(week_start: date) -> None:
    current = quests.monday(quality.today())
    if week_start.weekday() != 0:
        raise HTTPException(422, "A quest belongs to a week; use its Monday.")
    if week_start not in (current, current + timedelta(days=7)):
        raise HTTPException(422, "A quest can be set for this week or next week.")


@router.get("")
def read(week: date | None = Query(default=None)) -> dict:
    today = quality.today()
    current = quests.monday(today)
    start = quests.monday(week or today)
    if start > current + timedelta(days=7):
        raise HTTPException(422, "That week is too far ahead.")
    review = repo.get_review(start - timedelta(days=7))      # the plan written the Sunday before
    return {
        "week_start": start.isoformat(),
        "is_current": start == current,
        "editable": start in (current, current + timedelta(days=7)),
        "quest": quests.progress(start, today),
        "plan": ({"plan_if": review["plan_if"], "plan_then": review["plan_then"]}
                 if review and (review["plan_if"] or review["plan_then"]) else None),
        "templates": quests.templates(),
    }


@router.put("/{week_start}")
def put(week_start: date, body: QuestBody) -> dict:
    _editable_week(week_start)
    try:
        saved = quests.save(week_start, body.kind, body.target, body.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"saved": True, **saved}


@router.delete("/{week_start}", status_code=204)
def clear(week_start: date) -> None:
    _editable_week(week_start)
    repo.delete_quest(week_start)
