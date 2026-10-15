"""Weekly quest: one measurable goal for a week, scored from data Lifey already keeps.

The week's if-then plan from the review is free text. A quest is the part of it that can be
checked, so Lifey can say plainly whether the week met it.

Rules, the same ones the rest of Lifey follows:
- A day with no entries or a night with no recording is "unknown". It is never a pass and never
  a fail, and it lowers what the week can still reach.
- Today is "pending" for anything that can still change before the day ends.
- Nothing is stored about progress. It is scored on every read from the journal and the watch.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import entries as e
from . import habits as h
from . import repo

KINDS = ("habit_free", "sleep_hours", "bed_before", "training", "learning_sessions")
SLEEP_HOURS_CHOICES = (6.5, 7.0, 7.5, 8.0)
BED_TIME_CHOICES = ("22:00", "22:30", "23:00", "23:30", "00:00")
DEFAULT_TARGET = {"habit_free": 5, "sleep_hours": 5, "bed_before": 4, "training": 4, "learning_sessions": 3}


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _clock_minutes(hhmm: str) -> int:
    """Minutes after 18:00, so 23:30 and 00:30 sit in the right order (same scale as sleep_report)."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    return (hour * 60 + minute - 18 * 60) % (24 * 60)


def validate(kind: str, target: int, params: dict, habit_tags: dict[str, str]) -> dict:
    """Clean params for `kind` or raise ValueError with a message that is safe to show."""
    if kind not in KINDS:
        raise ValueError("Pick one of the quest types.")
    if not isinstance(target, int) or isinstance(target, bool) or not 1 <= target <= 7:
        raise ValueError("The target is between 1 and 7.")
    params = params or {}
    if kind in ("habit_free", "learning_sessions"):
        tag = str(params.get("tag") or "")
        if tag not in habit_tags:
            raise ValueError("Pick a habit from your list.")
        return {"tag": tag}
    if kind == "sleep_hours":
        try:
            hours = float(params.get("hours"))
        except (TypeError, ValueError):
            raise ValueError("Pick the hours of sleep.") from None
        if hours not in SLEEP_HOURS_CHOICES:
            raise ValueError("Pick the hours of sleep.")
        return {"hours": hours}
    if kind == "bed_before":
        time = str(params.get("time") or "")
        if time not in BED_TIME_CHOICES:
            raise ValueError("Pick a bedtime.")
        return {"time": time}
    return {}


def label(kind: str, target: int, params: dict, habit_tags: dict[str, str]) -> str:
    if kind == "habit_free":
        name = habit_tags.get(params.get("tag", ""), e.habit_label(params.get("tag", "")))
        return f"No {name.lower()} on {target} of 7 days"
    if kind == "sleep_hours":
        return f"{params['hours']:g} hours or more on {target} nights"
    if kind == "bed_before":
        return f"In bed before {params['time']} on {target} nights"
    if kind == "learning_sessions":
        name = habit_tags.get(params.get("tag", ""), e.habit_label(params.get("tag", "")))
        return f"{target} {name.lower()} session{'' if target == 1 else 's'}"
    return f"{target} training session{'' if target == 1 else 's'}"


def _day_states(kind: str, params: dict, days: list[date], today: date, *, grid_rows: list[dict],
                nights: dict[date, dict], trained: set[date]) -> list[dict]:
    from .. import sleep_report as sr

    cells = []
    if kind == "habit_free":
        row = next((r for r in grid_rows if r["tag"] == params["tag"]), None)
        by_day = {c["date"]: c["state"] for c in (row["cells"] if row else [])}
        for d in days:
            if d >= today:
                state = "pending"                     # the day is not over, so it can still change
            else:
                raw = by_day.get(d.isoformat(), "unknown")
                state = {"none": "pass", "logged": "fail"}.get(raw, "unknown")
            cells.append({"date": d.isoformat(), "state": state})
        return cells

    if kind == "learning_sessions":
        row = next((r for r in grid_rows if r["tag"] == params["tag"]), None)
        by_day = {c["date"]: c["state"] for c in (row["cells"] if row else [])}
        for d in days:
            raw = by_day.get(d.isoformat(), "unknown")
            if raw == "logged":
                state = "pass"
            elif d >= today:
                state = "pending"
            else:
                # Not practising is not a failure; a day with nothing written down is simply unknown.
                state = "rest" if raw == "none" else "unknown"
            cells.append({"date": d.isoformat(), "state": state})
        return cells

    if kind in ("sleep_hours", "bed_before"):
        for d in days:
            night = nights.get(d)
            if d > today:
                state = "pending"
            elif night is None or sr.kind(night) != "recorded":
                # Today's night may simply not have synced yet.
                state = "pending" if d == today else "unknown"
            elif kind == "sleep_hours":
                state = "pass" if night["hours"] >= params["hours"] else "fail"
            elif night.get("bed_min") is None:
                state = "unknown"
            else:
                state = "pass" if night["bed_min"] <= _clock_minutes(params["time"]) else "fail"
            cells.append({"date": d.isoformat(), "state": state})
        return cells

    for d in days:                                    # training: a rest day is not a failure
        if d in trained:
            state = "pass"
        elif d >= today:
            state = "pending"
        else:
            state = "rest"
        cells.append({"date": d.isoformat(), "state": state})
    return cells


def evaluate(quest: dict, days: list[date], today: date, *, grid_rows: list[dict],
             nights: dict[date, dict], trained: set[date], habit_tags: dict[str, str]) -> dict:
    cells = _day_states(quest["kind"], quest["params"], days, today,
                        grid_rows=grid_rows, nights=nights, trained=trained)
    count = lambda s: sum(1 for c in cells if c["state"] == s)       # noqa: E731
    passed, pending, target = count("pass"), count("pending"), quest["target"]
    if passed >= target:
        status = "met"
    elif passed + pending < target:
        status = "missed"
    elif passed + pending == target:
        status = "at_risk"            # every remaining day has to count
    else:
        status = "on_track"
    return {
        "week_start": days[0].isoformat(),
        "kind": quest["kind"],
        "target": target,
        "params": quest["params"],
        "label": label(quest["kind"], target, quest["params"], habit_tags),
        "status": status,
        "passed": passed,
        "failed": count("fail"),
        "unknown": count("unknown"),
        "pending": pending,
        "days": cells,
    }


def render(q: dict) -> str:
    """Plain text for the bot: facts, no cheering."""
    verdict = {
        "met": "Met.",
        "missed": "Missed.",
        "at_risk": "At risk: every remaining day has to count.",
        "on_track": "On track.",
    }[q["status"]]
    parts = [f"Done {q['passed']} of {q['target']}"]
    if q["failed"]:
        parts.append(f"missed {q['failed']}")
    if q["unknown"]:
        parts.append(f"no data {q['unknown']}")
    if q["pending"]:
        parts.append(f"{q['pending']} to go")
    mark = {"pass": "ok", "fail": "miss", "unknown": "no data", "pending": "-", "rest": "rest"}
    week = " | ".join(f"{date.fromisoformat(c['date']):%a} {mark[c['state']]}" for c in q["days"])
    return f"Quest: {q['label']}\n{', '.join(parts)}. {verdict}\n{week}"


# ---------- database-backed ----------

def habit_tags() -> dict[str, str]:
    """tag -> label for the built-in habits and the user's own."""
    out = {tag: lab for tag, (lab, _unit) in e.HABIT_TAGS.items()}
    out.update({r["tag"]: r["label"] for r in repo.list_habits()})
    return out


def templates() -> dict:
    return {
        "habits": [{"tag": t, "label": lab} for t, lab in habit_tags().items()],
        "sleep_hours": list(SLEEP_HOURS_CHOICES),
        "bed_times": list(BED_TIME_CHOICES),
        "default_target": DEFAULT_TARGET,
    }


def get(week_start: date) -> dict | None:
    return repo.get_quest(week_start)


def save(week_start: date, kind: str, target: int, params: dict) -> dict:
    clean = validate(kind, target, params, habit_tags())
    repo.save_quest(week_start, kind, target, json.dumps(clean))
    return {"week_start": week_start.isoformat(), "kind": kind, "target": target, "params": clean}


def progress(week_start: date, today: date) -> dict | None:
    """The quest for `week_start` scored against the data so far, or None when none was set."""
    from .. import db
    from .. import sleep_report as sr
    from ..bot import store, training_plan

    quest = repo.get_quest(week_start)
    if quest is None:
        return None
    days = [week_start + timedelta(days=i) for i in range(7)]
    tags = habit_tags()
    grid_rows: list[dict] = []
    nights: dict[date, dict] = {}
    trained: set[date] = set()
    if week_start <= today:
        end = min(days[-1], today)
        logs = store.get_activity_logs_between(week_start.isoformat(), end.isoformat())
        extra = {r["tag"]: (r["label"], r["unit"]) for r in repo.list_habits()}
        grid_rows = h.habit_grid(logs, days, extra)
        with db.connect() as conn:
            span = (end - week_start).days + 1
            nights = {date.fromisoformat(n["date"]): n for n in sr.load_nights(conn, end, span)}
        look_back = (today - week_start).days + 14
        activities = store.get_activities_df(days=look_back)
        trained = set(training_plan.trained_sessions(
            store.get_training_logs(days=look_back), [] if activities.empty else activities.to_dict("records")))
    return evaluate(quest, days, today, grid_rows=grid_rows, nights=nights, trained=trained, habit_tags=tags)
