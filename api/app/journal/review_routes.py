"""The weekly review: GET assembles a week, PUT saves the reflection."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.deps import current_user
from ..bot import quit_tracker, store, training_plan
from ..health import quality
from . import entries as e
from . import habit_routes, learning, repo
from . import habits as h
from . import review as r

router = APIRouter(prefix="/api/review", tags=["review"], dependencies=[Depends(current_user)])

LOOKBACK_WEEKS = 8


class Reflection(BaseModel):
    went_well: str = Field(default="", max_length=4000)
    got_in_way: str = Field(default="", max_length=4000)
    learned: str = Field(default="", max_length=4000)
    plan_if: str = Field(default="", max_length=300)
    plan_then: str = Field(default="", max_length=300)
    recall: str | None = Field(default=None, max_length=4000)       # None keeps what is stored
    learn_slot: str | None = Field(default=None, max_length=300)



def _week_label(start: date) -> str:
    end = start + timedelta(days=6)
    same_month = start.month == end.month
    left = f"{start.day}" if same_month else f"{start.day} {start:%b}"
    return f"Week {start.isocalendar().week} · {left} – {end.day} {end:%b}"


@router.get("")
def week_review(week: date | None = Query(default=None)) -> dict:
    today = quality.today()
    current = r.monday(today)
    start = r.monday(week or today)
    if start > current:
        raise HTTPException(422, "That week has not started yet.")
    days = [start + timedelta(days=i) for i in range(7)]
    prev_days = [start - timedelta(days=7) + timedelta(days=i) for i in range(7)]

    history_start = start - timedelta(weeks=LOOKBACK_WEEKS)
    end = min(days[-1], today)
    logs_history = store.get_activity_logs_between(history_start.isoformat(), end.isoformat())
    week_logs = [l for l in logs_history if start.isoformat() <= str(l["date"])[:10] <= days[-1].isoformat()]

    frame = store.get_df(limit=120)
    daily_rows = [] if frame.empty else frame.to_dict("records")
    daily = r._by_date(daily_rows)

    quit_logs = store.get_quit_logs()
    summary = quit_tracker.summarize(quit_logs, min(today, days[-1]))
    strip = h.quit_strip(week_logs, days)
    training_logs = store.get_training_logs(days=(today - start).days + 14)
    activities = store.get_activities_df(days=(today - start).days + 14)
    trained = training_plan.trained_sessions(training_logs, [] if activities.empty else activities.to_dict("records"))

    cat = habit_routes.catalog()
    labels = {c["tag"]: c["label"] for c in cat}
    extra = {c["tag"]: (c["label"], c["unit"]) for c in cat if not c["builtin"]}
    grid = [row for row in h.habit_grid(week_logs, days, extra) if row["days"] > 0]
    patterns = r.pattern_candidates(logs_history, daily_rows, [row["tag"] for row in grid], today, labels)

    reflection = repo.get_review(start)
    last_week = repo.get_review(start - timedelta(days=7))
    first = repo.first_activity_date()
    return {
        "week_start": start.isoformat(),
        "week_end": days[-1].isoformat(),
        "label": _week_label(start),
        "is_current": start == current,
        "prev_week": (start - timedelta(days=7)).isoformat() if first and start - timedelta(days=7) >= r.monday(first) else None,
        "next_week": (start + timedelta(days=7)).isoformat() if start < current else None,
        "numbers": r._numbers(days, prev_days, daily, week_logs, summary, strip, set(trained), today),
        "notes": r.notes_of_the_week(week_logs),
        "habits": grid,
        "patterns": patterns,
        "min_nights": r.MIN_NIGHTS,
        "reflection": reflection,
        "learning": _learning_block(week_logs, days, today, last_week),
        "last_plan": ({"plan_if": last_week["plan_if"], "plan_then": last_week["plan_then"]}
                      if last_week and (last_week["plan_if"] or last_week["plan_then"]) else None),
        "habit_cues": [{"label": c["label"], "cue_if": c["cue_if"], "cue_then": c["cue_then"]}
                       for c in cat if c.get("cue_if") or c.get("cue_then")],
    }


def _learning_block(week_logs: list[dict], days: list[date], today: date, last_week: dict | None) -> dict:
    """The current focus against this week's journal entries. Nothing is graded here."""
    active = repo.active_focus()
    block: dict = {"focus": None, "renewal": learning.renewal(active, today), "week": None,
                   "last_recall": (last_week or {}).get("recall") or None,
                   "last_slot": (last_week or {}).get("learn_slot") or None}
    if active:
        keep = ("id", "topic", "category", "outcome", "plan_if", "plan_then", "month")
        block["focus"] = {k: active[k] for k in keep}
        block["week"] = learning.sessions(week_logs, active["habit_tag"], [d for d in days if d <= today])
    return block


@router.put("/{week_start}")
def save_reflection(week_start: date, body: Reflection) -> dict:
    if week_start.weekday() != 0:
        raise HTTPException(422, "A review belongs to a week; use its Monday.")
    if week_start > r.monday(quality.today()):
        raise HTTPException(422, "That week has not started yet.")
    repo.save_review(week_start, body.went_well.strip(), body.got_in_way.strip(), body.learned.strip(),
                     body.plan_if.strip(), body.plan_then.strip(),
                     None if body.recall is None else body.recall.strip(),
                     None if body.learn_slot is None else body.learn_slot.strip())
    return {"saved": True, "week_start": week_start.isoformat()}
