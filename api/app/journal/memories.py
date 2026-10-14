"""On this day: what the journal holds from today's date in earlier months and years.

Only things you wrote or attached count: a free note or a file. Habit taps and the bot's default
notes are not memories. When a date has nothing worth showing, it is left out, never padded.
"""
from __future__ import annotations

import calendar
from datetime import date

from . import entries as e

OFFSETS = ((1, "A month ago"), (3, "Three months ago"), (6, "Six months ago"),
           (12, "A year ago"), (24, "Two years ago"))
MAX_NOTE = 600


def months_back(day: date, months: int) -> date:
    """The same day of the month `months` earlier, clamped to the month's length (31 Mar -> 28 Feb)."""
    index = day.year * 12 + (day.month - 1) - months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def pick(logs: list[dict], files: dict[int, list[dict]]) -> dict | None:
    """The best memory among one day's log rows: a photo first, then the longest note."""
    best: tuple[tuple[int, int], dict] | None = None
    for log in logs:
        if e.kind(log) != "note":
            continue
        note = e._text(log.get("note"))
        if note.lower() in e.BOT_DEFAULT_NOTES:
            note = ""
        attached = files.get(log.get("id"), [])
        image = next((a for a in attached if a.get("has_thumb")), None)
        if not note and not attached:
            continue
        time_text, _ = e.entry_time(log)
        item = {
            "log_id": log.get("id"),
            "date": str(log["date"])[:10],
            "time": time_text,
            "note": note[:MAX_NOTE],
            "attachment": image,
            "files": len(attached),
        }
        score = (1 if image else 0, len(note))
        if best is None or score > best[0]:
            best = (score, item)
    return best[1] if best else None


def for_day(today: date) -> list[dict]:
    """Memories for `today`, oldest offset last. Needs the database."""
    from .. import attachments
    from ..bot import store

    out = []
    for months, label in OFFSETS:
        day = months_back(today, months)
        if day >= today:
            continue
        logs = store.get_activity_logs_between(day.isoformat(), day.isoformat())
        if not logs:
            continue
        ids = [l["id"] for l in logs if l.get("id") is not None]
        item = pick(logs, attachments.for_logs(ids))
        if item:
            out.append({**item, "label": label, "months": months})
    return out


def best(memories: list[dict]) -> dict | None:
    """The one to send: a photo if any memory has one, otherwise the nearest note."""
    return next((m for m in memories if m["attachment"]), memories[0] if memories else None)
