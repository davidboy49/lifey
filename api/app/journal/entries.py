"""Journal entries for display: classification and grouping.

A port of the pure data half of vidhealth's journal_ui (the HTML half is the
web app's job now). Rules worth keeping:
- a day's mood and energy rows merge into one check-in;
- notes the bot filled in itself (they only repeat the title) are hidden;
- a day with nothing logged is unknown, never a clean day;
- an entry saved on a later day than it happened is flagged `recalled`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

# Canonical habit tags as the bot saves them -> (label, unit).
HABIT_TAGS = {
    "alcohol": ("Alcohol", "drinks"),
    "late_caffeine": ("Late caffeine", "times"),
    "late_meal": ("Late meal", "times"),
    "late_screen": ("Late screen", "times"),
    "nicotine": ("Nicotine", "times"),
    "mental_stress": ("High stress", "times"),
}
TAG_ALIASES = {"late_screen_time": "late_screen", "high_mental_stress": "mental_stress"}
BOT_DEFAULT_NOTES = {"late heavy meal", "late caffeine", "late screen time", "nicotine",
                     "high mental stress", "1 standard drink", "2 standard drinks", "3+ drinks"}
QUIT_TITLES = {"master": "Slip", "urge_resisted": "Urge resisted", "clean_day": "Clean day checked"}

KIND_FILTERS = {
    "all": None,
    "habit": {"habit"},
    "quit": {"quit", "reason"},
    "note": {"note"},
    "checkin": {"checkin"},
    "training": {"training"},
}


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat", "<na>"} else text


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _fmt(number: float) -> str:
    return f"{number:g}"


def slug(tag: str) -> str:
    return "_".join(_text(tag).lower().replace("-", " ").split())


def habit_tag(log: dict) -> str:
    tag = _text(log.get("tag")).lower()
    return TAG_ALIASES.get(tag, tag)


def habit_label(tag: str) -> str:
    return HABIT_TAGS[tag][0] if tag in HABIT_TAGS else tag.replace("_", " ").strip().capitalize() or "Habit"


def habit_unit(tag: str) -> str:
    return HABIT_TAGS[tag][1] if tag in HABIT_TAGS else "times"


def kind(log: dict) -> str:
    category, tag = log.get("category"), log.get("tag")
    if category == "training":
        return "training"
    if category == "wellbeing":
        return "checkin"
    if category == "master" or tag == "master":
        return "quit"
    if category == "quit_reason":
        return "reason"
    if category == "unholy_habit":
        return "habit"
    return "note"


def entry_time(log: dict) -> tuple[str, bool]:
    """(HH:MM, True) when the time it happened was recorded, else the time it was saved."""
    occurred = _text(log.get("occurred_at"))
    if occurred:
        return occurred[:5], True
    stamp = _text(log.get("timestamp"))
    return (stamp[11:16] if len(stamp) >= 16 else ""), False


def recalled(log: dict) -> bool:
    """Saved on a later day than the one it is about."""
    stamp = _text(log.get("timestamp"))
    return len(stamp) >= 10 and stamp[:10] > str(log["date"])[:10]


def amount_text(tag: str, value) -> str:
    number = _number(value)
    if number is None:
        return ""
    if tag == "alcohol":
        return f"{_fmt(number)} drink{'' if number == 1 else 's'}"
    return "" if number == 1 else f"×{_fmt(number)}"


def build_entries(logs: list[dict]) -> list[dict]:
    """One display entry per log row; a day's mood and energy rows merge into one check-in."""
    entries, checkins = [], {}
    for log in logs:
        k = kind(log)
        day = _day(log["date"])
        time_text, occurred = entry_time(log)
        was_recalled = recalled(log)
        if k == "checkin":
            entry = checkins.get(day)
            if entry is None:
                entry = checkins[day] = {"date": day.isoformat(), "kind": k, "title": "Check-in",
                                         "subtitle": "", "badges": {}, "note": "", "ids": [],
                                         "time": time_text, "time_recorded": occurred, "recalled": was_recalled}
                entries.append(entry)
            tag = _text(log.get("tag")).lower()
            number = _number(log.get("value"))
            if tag in ("mood", "energy") and number is not None and tag not in entry["badges"]:
                entry["badges"][tag] = f"{tag.capitalize()} {_fmt(number)}/5"
            if _text(log.get("note")) and not entry["note"]:
                entry["note"] = _text(log.get("note"))
            entry["ids"].append(log.get("id"))
            if time_text and (not entry["time"] or time_text < entry["time"]):
                entry["time"], entry["time_recorded"] = time_text, occurred
            continue

        note = _text(log.get("note"))
        badges, subtitle = [], ""
        if k == "habit":
            tag = habit_tag(log)
            title, subtitle = habit_label(tag), "Sleep disruptor"
            amount = amount_text(tag, log.get("value"))
            badges = [amount] if amount else []
        elif k == "quit":
            title = QUIT_TITLES.get(_text(log.get("tag")), habit_label(_text(log.get("tag"))))
            subtitle = "Quit tracker"
        elif k == "reason":
            title, subtitle = "Reason to quit", "Quit tracker"
        elif k == "training":
            title, subtitle = note or habit_label(_text(log.get("tag"))), "Training"
            note = ""
        else:
            title = "Note"
        if note.lower() in BOT_DEFAULT_NOTES or note.lower() == title.lower():
            note = ""
        entries.append({"date": day.isoformat(), "kind": k, "title": title, "subtitle": subtitle,
                        "badges": badges, "note": note, "ids": [log.get("id")],
                        "time": time_text, "time_recorded": occurred, "recalled": was_recalled})
    for entry in entries:
        if isinstance(entry["badges"], dict):
            entry["badges"] = [entry["badges"][t] for t in ("mood", "energy") if t in entry["badges"]]
    return entries


def day_groups(entries: list[dict], start: date, end: date, show_gaps: bool = True) -> list[dict]:
    """Newest day first. Consecutive days without entries collapse into one unknown group."""
    by_day = defaultdict(list)
    for entry in entries:
        by_day[entry["date"]].append(entry)
    groups, gap = [], []

    def flush():
        if gap and show_gaps:
            groups.append({"empty": True, "first": gap[-1].isoformat(), "last": gap[0].isoformat()})
        gap.clear()

    day = end
    while day >= start:
        if by_day.get(day.isoformat()):
            flush()
            items = sorted(by_day[day.isoformat()], key=lambda e: e["time"], reverse=True)
            groups.append({"empty": False, "date": day.isoformat(), "entries": items})
        else:
            gap.append(day)
        day -= timedelta(days=1)
    flush()
    return groups


def latest_value(logs: list[dict], tag: str):
    rows = [l for l in logs if l.get("category") == "wellbeing" and l.get("tag") == tag
            and _number(l.get("value")) is not None]
    rows.sort(key=lambda l: (_text(l.get("timestamp")), l.get("id") or 0))
    return _number(rows[-1]["value"]) if rows else None
