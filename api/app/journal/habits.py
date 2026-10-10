"""Habit grid, quit strip and mood/energy rows from journal entries.

Pure functions over activity-log rows (dicts) so they test without a database.
Three states per cell, kept distinct on purpose:

    logged   the habit was recorded that day
    none     the day has entries, but not this habit
    unknown  nothing at all was logged that day (never read as "clean")
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from . import entries as e


def window(end: date, weeks: int) -> list[date]:
    """Whole Monday-to-Sunday weeks, ending with the week that contains `end`, cut at `end`."""
    start = end - timedelta(days=end.weekday()) - timedelta(weeks=weeks - 1)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _level(amount: float) -> int:
    return 1 if amount <= 1 else 2 if amount <= 2 else 3


def habit_grid(logs: list[dict], days: list[date], extra: dict[str, tuple[str, str]] | None = None) -> list[dict]:
    """One row per habit. `extra` maps custom tag -> (label, unit)."""
    catalog = {**e.HABIT_TAGS, **(extra or {})}
    logged_days = {e._day(l["date"]) for l in logs}
    amounts: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for log in logs:
        if e.kind(log) == "habit":
            number = e._number(log.get("value"))
            amounts[e.habit_tag(log)][e._day(log["date"])] += number if number is not None else 1.0
    tags = list(catalog) + sorted(t for t in amounts if t not in catalog)

    rows = []
    for tag in tags:
        label, unit = catalog.get(tag, (e.habit_label(tag), "times"))
        cells, day_count, total = [], 0, 0.0
        for day in days:
            if day not in logged_days:
                cells.append({"date": day.isoformat(), "state": "unknown"})
                continue
            amount = amounts[tag].get(day, 0.0)
            if not amount:
                cells.append({"date": day.isoformat(), "state": "none"})
                continue
            day_count += 1
            total += amount
            cells.append({"date": day.isoformat(), "state": "logged", "amount": amount, "level": _level(amount)})
        rows.append({"tag": tag, "label": label, "unit": unit, "cells": cells,
                     "days": day_count, "total": total, "builtin": tag in e.HABIT_TAGS})
    return rows


def quit_strip(logs: list[dict], days: list[date]) -> list[dict]:
    logged_days = {e._day(l["date"]) for l in logs}
    tags: dict[date, set[str]] = defaultdict(set)
    for log in logs:
        if e.kind(log) == "quit":
            tags[e._day(log["date"])].add(e._text(log.get("tag")))
    cells = []
    for day in days:
        iso = day.isoformat()
        if day not in logged_days:
            cells.append({"date": iso, "state": "unknown"})
        elif "master" in tags[day]:
            cells.append({"date": iso, "state": "slip"})
        else:
            urge = "urge_resisted" in tags[day]
            checked = "clean_day" in tags[day]
            cells.append({"date": iso, "state": "clean" if (checked or urge) else "unchecked", "urge": urge})
    return cells


def wellbeing_rows(logs: list[dict], days: list[date]) -> list[dict]:
    logged_days = {e._day(l["date"]) for l in logs}
    rows = []
    for tag in ("mood", "energy"):
        by_day: dict[date, list[dict]] = defaultdict(list)
        for log in logs:
            if log.get("category") == "wellbeing" and log.get("tag") == tag:
                by_day[e._day(log["date"])].append(log)
        cells, values = [], []
        for day in days:
            iso = day.isoformat()
            if day not in logged_days:
                cells.append({"date": iso, "state": "unknown"})
                continue
            value = e.latest_value(by_day.get(day, []), tag)
            if value is None:
                cells.append({"date": iso, "state": "none"})
                continue
            values.append(value)
            cells.append({"date": iso, "state": "logged", "value": value, "level": min(5, max(1, round(value)))})
        rows.append({"tag": tag, "label": tag.capitalize(), "cells": cells,
                     "average": sum(values) / len(values) if values else None, "count": len(values)})
    return rows


def quit_card(summary: dict, strip: list[dict], today: date) -> dict | None:
    """Days free over the last 30 and the best run: a slip is one day, not a reset to zero."""
    start = summary.get("tracking_start")
    if start is None:
        return None
    cutoff = today - timedelta(days=29)
    first = max(start, cutoff)
    # Days from `first` to today; a day counts as free unless a slip was logged on it.
    slip_days = {c["date"] for c in strip if c["state"] == "slip"}
    span = [first + timedelta(days=i) for i in range((today - first).days + 1)]
    tracked = len(span)
    free = sum(1 for d in span if d.isoformat() not in slip_days)
    return {
        "current_run": summary["current_streak"],
        "best_run": summary["best_streak"],
        "urges_this_run": summary["urges_this_streak"],
        "slips_7d": summary["relapses_7d"],
        "slips_30d": summary["relapses_30d"],
        "free_days_30": free,
        "tracked_days_30": tracked,
        "free_pct_30": round(100 * free / tracked) if tracked else None,
        "tracking_since": start.isoformat(),
        "relapsed_today": summary["relapsed_today"],
    }
