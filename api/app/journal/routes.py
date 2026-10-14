"""Journal API: read the timeline, add an entry for any past day, remove an entry."""
from __future__ import annotations

import datetime as dt
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from .. import attachments
from ..auth.deps import current_user
from ..bot import quit_tracker, store
from ..health import quality
from . import entries, memories
from . import habits as habit_views

router = APIRouter(prefix="/api/journal", tags=["journal"], dependencies=[Depends(current_user)])

MAX_BACKDATE_DAYS = 400
QUIT_ACTIONS = {"slip": ("master", 1.0), "urge": ("urge_resisted", 1.0), "clean": ("clean_day", 0.0)}


class NewEntry(BaseModel):
    kind: Literal["habit", "quit", "checkin", "note"]
    # habit
    habit: str | None = Field(default=None, max_length=48)
    amount: float | None = Field(default=None, gt=0, le=500)
    # quit
    action: Literal["slip", "urge", "clean"] | None = None
    # check-in
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    # shared
    note: str = Field(default="", max_length=2000)
    date: dt.date | None = None       # the day it happened; defaults to today
    time: str | None = None           # HH:MM it happened; defaults to now

    @field_validator("time")
    @classmethod
    def _hhmm(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must be HH:MM") from exc
        return v


def _local_now() -> datetime:
    return datetime.now(quality.user_timezone())


@router.get("")
def timeline(days: int = Query(7, ge=1, le=90), kind: str = Query("all")) -> dict:
    if kind not in entries.KIND_FILTERS:
        raise HTTPException(422, f"kind must be one of {sorted(entries.KIND_FILTERS)}")
    today = quality.today()
    start = today - timedelta(days=days - 1)
    logs = store.get_activity_logs_between(start.isoformat(), today.isoformat())
    wanted = entries.KIND_FILTERS[kind]
    shown = [e for e in entries.build_entries(logs) if wanted is None or e["kind"] in wanted]
    files = attachments.for_logs([i for e in shown for i in e["ids"]])
    for e in shown:
        e["attachments"] = [a for i in e["ids"] for a in files.get(i, [])]
    groups = entries.day_groups(shown, start, today, show_gaps=wanted is None)

    today_logs = [l for l in logs if str(l["date"]) == today.isoformat()]
    habits = [l for l in today_logs if entries.kind(l) == "habit"]
    quit_summary = quit_tracker.summarize(store.get_quit_logs(), today)
    tracking = quit_summary.get("tracking_start") is not None
    last30 = [today - timedelta(days=i) for i in range(29, -1, -1)]
    card = habit_views.quit_card(
        quit_summary,
        habit_views.quit_strip(store.get_activity_logs_between(last30[0].isoformat(), today.isoformat()), last30),
        today)
    return {
        "today": today.isoformat(), "start": start.isoformat(), "days": days, "kind": kind,
        "summary": {
            "mood": entries.latest_value(today_logs, "mood"),
            "energy": entries.latest_value(today_logs, "energy"),
            "habits_today": list(dict.fromkeys(entries.habit_label(entries.habit_tag(l)) for l in habits)),
            "notes_today": sum(1 for l in today_logs if entries.kind(l) == "note"),
            "days_free": quit_summary["current_streak"] if tracking else None,
            "best_run": quit_summary["best_streak"] if tracking else None,
            # The headline number: a slip is one day, not a reset to zero.
            "free_days_30": card["free_days_30"] if card else None,
            "tracked_days_30": card["tracked_days_30"] if card else None,
        },
        "groups": groups,
        "count": sum(len(g["entries"]) for g in groups if not g["empty"]),
    }


@router.get("/memories")
def on_this_day() -> dict:
    """Notes and photos from this date a month, three, six, twelve and twenty-four months ago."""
    today = quality.today()
    return {"today": today.isoformat(), "memories": memories.for_day(today)}


@router.post("", status_code=201)
def add_entry(body: NewEntry) -> dict:
    now = _local_now()
    today = now.date()
    day = body.date or today
    if day > today:
        raise HTTPException(422, "That date is in the future.")
    if (today - day).days > MAX_BACKDATE_DAYS:
        raise HTTPException(422, f"Entries can go back at most {MAX_BACKDATE_DAYS} days.")
    occurred = body.time or now.strftime("%H:%M")
    if day == today and body.time and body.time > now.strftime("%H:%M"):
        raise HTTPException(422, "That time is still in the future.")
    note = body.note.strip()
    ids: list[int] = []

    def save(category: str, tag: str, value: float | None, text: str = "") -> None:
        ids.append(store.log_activity(date_str=day.isoformat(), category=category, tag=tag,
                                      note=text, value=value, occurred_at=occurred))

    if body.kind == "habit":
        tag = entries.slug(body.habit or "")
        if not tag:
            raise HTTPException(422, "Name the habit.")
        save("unholy_habit", entries.TAG_ALIASES.get(tag, tag), body.amount or 1.0, note)
    elif body.kind == "quit":
        if body.action is None:
            raise HTTPException(422, "Choose what happened.")
        tag, value = QUIT_ACTIONS[body.action]
        save(quit_tracker.CATEGORY, tag, value, note)
    elif body.kind == "checkin":
        if body.mood is None and body.energy is None:
            raise HTTPException(422, "Pick a mood or an energy level.")
        for tag, value in (("mood", body.mood), ("energy", body.energy)):
            if value is not None:
                save(quit_tracker.WELLBEING_CATEGORY, tag, float(value), note)
                note = ""
    else:
        if not note:
            raise HTTPException(422, "Write the note first.")
        save("free_note", "note", None, note)

    return {"ids": ids, "date": day.isoformat(), "time": occurred,
            "recalled": day < today}


@router.delete("/{entry_id}", status_code=204)
def remove_entry(entry_id: int) -> None:
    if not store.delete_activity_log(entry_id):
        raise HTTPException(404, "That entry was already removed.")
