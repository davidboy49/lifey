"""Habits: the grid, the softened quit card, and the user's own habit list."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.deps import current_user
from ..bot import quit_tracker, store
from ..health import quality
from . import entries as e
from . import habits as h
from . import repo

router = APIRouter(prefix="/api/habits", tags=["habits"], dependencies=[Depends(current_user)])


class NewHabit(BaseModel):
    label: str = Field(min_length=1, max_length=48)
    unit: str = Field(default="times", min_length=1, max_length=24)
    cue_if: str | None = Field(default=None, max_length=200)
    cue_then: str | None = Field(default=None, max_length=200)


class HabitPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=48)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    cue_if: str | None = Field(default=None, max_length=200)
    cue_then: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


def catalog() -> list[dict]:
    """Built-in habits first, then the user's own."""
    out = [{"tag": t, "label": lab, "unit": unit, "builtin": True, "cue_if": None, "cue_then": None}
           for t, (lab, unit) in e.HABIT_TAGS.items()]
    out += [{**row, "builtin": False} for row in repo.list_habits()]
    return out


@router.get("")
def overview(weeks: int = Query(5, ge=1, le=26)) -> dict:
    today = quality.today()
    days = h.window(today, weeks)
    logs = store.get_activity_logs_between(days[0].isoformat(), today.isoformat())
    extra = {c["tag"]: (c["label"], c["unit"]) for c in catalog() if not c["builtin"]}
    strip_days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    quit_logs = store.get_quit_logs()
    summary = quit_tracker.summarize(quit_logs, today)
    strip = h.quit_strip(store.get_activity_logs_between(strip_days[0].isoformat(), today.isoformat()), strip_days)
    return {
        "today": today.isoformat(),
        "weeks": weeks,
        "days": [d.isoformat() for d in days],
        "habits": h.habit_grid(logs, days, extra),
        "wellbeing": h.wellbeing_rows(logs, days),
        "quit": {"card": h.quit_card(summary, strip, today), "strip": strip},
        "catalog": catalog(),
    }


@router.get("/catalog")
def habit_catalog() -> list[dict]:
    return catalog()


@router.post("", status_code=201)
def add_habit(body: NewHabit) -> dict:
    tag = e.slug(body.label)
    if not tag or len(tag) > 48 or not all(ch.isalnum() or ch == "_" for ch in tag):
        raise HTTPException(422, "Use letters and numbers in the habit name.")
    tag = e.TAG_ALIASES.get(tag, tag)
    if tag in e.HABIT_TAGS:
        raise HTTPException(409, "That is already one of the built-in habits.")
    if not repo.create_habit(tag, body.label.strip(), body.unit.strip(), (body.cue_if or "").strip() or None,
                             (body.cue_then or "").strip() or None):
        raise HTTPException(409, "You already have a habit with that name.")
    return {"tag": tag}


@router.patch("/{tag}")
def edit_habit(tag: str, body: HabitPatch) -> dict:
    fields = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(422, "Nothing to change.")
    if tag in e.HABIT_TAGS:
        raise HTTPException(409, "Built-in habits can't be edited.")
    if not repo.update_habit(tag, fields):
        raise HTTPException(404, "No such habit.")
    return {"tag": tag}
