"""Reminder times and switches, editable from the web.

The bot checks every minute; a reminder fires once a day when the local time
has reached its time (and no more than three hours have passed, so a restart
catches up but a long outage doesn't send a morning question at night).
Settings fall back to the old environment variables, then to the defaults.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, time, timedelta

from . import db

NAMES = {
    "morning_feeling": {"label": "Morning feeling", "env": "MORNING_FEELING_TIME", "time": "06:55"},
    "evening_checkin": {"label": "Evening check-in", "env": "HABIT_CHECKIN_TIME", "time": "22:00"},
}
CATCH_UP = timedelta(hours=3)
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def valid_time(value: object) -> bool:
    return isinstance(value, str) and bool(_TIME.match(value))


def _env_default(name: str) -> dict:
    spec = NAMES[name]
    raw = os.environ.get(spec["env"], "").strip().lower()
    if raw == "off":
        return {"enabled": False, "time": spec["time"]}
    return {"enabled": True, "time": raw if valid_time(raw) else spec["time"]}


def _read(conn, key: str) -> dict:
    row = conn.execute("SELECT value FROM journal.settings WHERE key=%s", (key,)).fetchone()
    return dict(row[0]) if row and isinstance(row[0], dict) else {}


def load() -> dict:
    with db.connect() as conn:
        stored = _read(conn, "reminders")
    out = {}
    for name in NAMES:
        merged = {**_env_default(name), **(stored.get(name) or {})}
        out[name] = {"enabled": bool(merged["enabled"]),
                     "time": merged["time"] if valid_time(merged["time"]) else NAMES[name]["time"]}
    return out


def save(changes: dict) -> dict:
    """Merge validated changes ({name: {enabled?, time?}}) into the stored settings."""
    current = load()
    for name, patch in changes.items():
        if name not in NAMES or not isinstance(patch, dict):
            raise ValueError(f"Unknown reminder {name!r}.")
        if "time" in patch:
            if not valid_time(patch["time"]):
                raise ValueError("Use a time like 06:55.")
            current[name]["time"] = patch["time"]
        if "enabled" in patch:
            if not isinstance(patch["enabled"], bool):
                raise ValueError("enabled must be true or false.")
            current[name]["enabled"] = patch["enabled"]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO journal.settings (key, value) VALUES ('reminders', %s::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
            (__import__("json").dumps(current),))
        conn.commit()
    return current


def due(now: datetime) -> list[str]:
    """Names that should fire now: enabled, time reached within the catch-up window, not sent today."""
    settings = load()
    with db.connect() as conn:
        sent = _read(conn, "reminder_state")
    today = now.date().isoformat()
    out = []
    for name, cfg in settings.items():
        if not cfg["enabled"] or sent.get(name) == today:
            continue
        hour, minute = (int(x) for x in cfg["time"].split(":"))
        target = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        if timedelta(0) <= now - target <= CATCH_UP:
            out.append(name)
    return out


def claim_daily(name: str, day: str) -> bool:
    """True the first time it is called for `name` on `day`, False after that (survives restarts)."""
    import json
    with db.connect() as conn:
        state = _read(conn, "reminder_state")
        if state.get(name) == day:
            return False
        state[name] = day
        conn.execute(
            "INSERT INTO journal.settings (key, value) VALUES ('reminder_state', %s::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()", (json.dumps(state),))
        conn.commit()
    return True


def mark_sent(name: str, day: str) -> None:
    import json
    with db.connect() as conn:
        state = _read(conn, "reminder_state")
        state[name] = day
        conn.execute(
            "INSERT INTO journal.settings (key, value) VALUES ('reminder_state', %s::jsonb) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()", (json.dumps(state),))
        conn.commit()
