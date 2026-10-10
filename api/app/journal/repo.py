"""Database access for custom habits and weekly reviews."""
from __future__ import annotations

from datetime import date

from .. import db as database


def _rows(sql: str, params=()) -> list[dict]:
    with database.connect() as conn:
        cur = conn.execute(sql, params)
        names = [c.name for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def list_habits(include_archived: bool = False) -> list[dict]:
    where = "" if include_archived else "WHERE NOT archived"
    return _rows(f"SELECT tag, label, unit, cue_if, cue_then, archived FROM journal.habits {where} ORDER BY created_at, tag")


def create_habit(tag: str, label: str, unit: str, cue_if: str | None, cue_then: str | None) -> bool:
    """False when the tag already exists."""
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.habits (tag, label, unit, cue_if, cue_then) VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (tag) DO NOTHING RETURNING tag""", (tag, label, unit, cue_if, cue_then)).fetchone()
        conn.commit()
        return row is not None


def update_habit(tag: str, fields: dict) -> bool:
    allowed = {k: v for k, v in fields.items() if k in {"label", "unit", "cue_if", "cue_then", "archived"}}
    if not allowed:
        return False
    assignments = ", ".join(f"{k}=%s" for k in allowed)
    with database.connect() as conn:
        n = conn.execute(f"UPDATE journal.habits SET {assignments} WHERE tag=%s", [*allowed.values(), tag]).rowcount
        conn.commit()
        return n > 0


def get_review(week_start: date) -> dict | None:
    rows = _rows("""SELECT week_start::text AS week_start, went_well, got_in_way, learned, plan_if, plan_then,
                           updated_at FROM journal.weekly_reviews WHERE week_start=%s""", (week_start,))
    return rows[0] if rows else None


def save_review(week_start: date, went_well: str, got_in_way: str, learned: str, plan_if: str, plan_then: str) -> None:
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO journal.weekly_reviews (week_start, went_well, got_in_way, learned, plan_if, plan_then)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (week_start) DO UPDATE SET went_well=excluded.went_well, got_in_way=excluded.got_in_way,
                 learned=excluded.learned, plan_if=excluded.plan_if, plan_then=excluded.plan_then, updated_at=NOW()""",
            (week_start, went_well, got_in_way, learned, plan_if, plan_then))
        conn.commit()


def first_activity_date() -> date | None:
    rows = _rows("SELECT LEAST((SELECT MIN(date) FROM journal.activity_logs), "
                 "(SELECT MIN(date) FROM health.daily_metrics)) AS d")
    return rows[0]["d"] if rows else None
