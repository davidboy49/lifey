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
                           recall, learn_slot, updated_at FROM journal.weekly_reviews WHERE week_start=%s""",
                 (week_start,))
    return rows[0] if rows else None


def save_review(week_start: date, went_well: str, got_in_way: str, learned: str, plan_if: str, plan_then: str,
                recall: str | None = None, learn_slot: str | None = None) -> None:
    """`recall` and `learn_slot` of None leave what is stored alone (an older client does not know them)."""
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO journal.weekly_reviews (week_start, went_well, got_in_way, learned, plan_if, plan_then,
                                                   recall, learn_slot)
               VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s,''),COALESCE(%s,''))
               ON CONFLICT (week_start) DO UPDATE SET went_well=excluded.went_well, got_in_way=excluded.got_in_way,
                 learned=excluded.learned, plan_if=excluded.plan_if, plan_then=excluded.plan_then,
                 recall=COALESCE(%s, journal.weekly_reviews.recall),
                 learn_slot=COALESCE(%s, journal.weekly_reviews.learn_slot), updated_at=NOW()""",
            (week_start, went_well, got_in_way, learned, plan_if, plan_then, recall, learn_slot, recall, learn_slot))
        conn.commit()


def get_quest(week_start: date) -> dict | None:
    rows = _rows("SELECT kind, target, params FROM journal.quests WHERE week_start=%s", (week_start,))
    if not rows:
        return None
    row = rows[0]
    return {"week_start": week_start.isoformat(), "kind": row["kind"], "target": row["target"],
            "params": row["params"] if isinstance(row["params"], dict) else {}}


def save_quest(week_start: date, kind: str, target: int, params_json: str) -> None:
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO journal.quests (week_start, kind, target, params) VALUES (%s,%s,%s,%s::jsonb)
               ON CONFLICT (week_start) DO UPDATE SET kind=excluded.kind, target=excluded.target,
                 params=excluded.params, updated_at=NOW()""",
            (week_start, kind, target, params_json))
        conn.commit()


def delete_quest(week_start: date) -> bool:
    with database.connect() as conn:
        n = conn.execute("DELETE FROM journal.quests WHERE week_start=%s", (week_start,)).rowcount
        conn.commit()
        return n > 0


def first_activity_date() -> date | None:
    rows = _rows("SELECT LEAST((SELECT MIN(date) FROM journal.activity_logs), "
                 "(SELECT MIN(date) FROM health.daily_metrics)) AS d")
    return rows[0]["d"] if rows else None


# ---------- learning focus and evidence shelf ----------

FOCUS_COLS = ("id, month::text AS month, topic, topic_key, category, outcome, plan_if, plan_then, why, habit_tag, "
              "status, result, next_step, closed_at, created_at")


def active_focus() -> dict | None:
    rows = _rows(f"SELECT {FOCUS_COLS} FROM journal.learning_focus WHERE status='active'")
    return rows[0] if rows else None


def get_focus(focus_id: int) -> dict | None:
    rows = _rows(f"SELECT {FOCUS_COLS} FROM journal.learning_focus WHERE id=%s", (focus_id,))
    return rows[0] if rows else None


def closed_focuses(limit: int = 12) -> list[dict]:
    return _rows(f"SELECT {FOCUS_COLS} FROM journal.learning_focus WHERE status='closed' "
                 "ORDER BY closed_at DESC, id DESC LIMIT %s", (limit,))


def create_focus(month: date, f: dict) -> dict | None:
    """The new active focus, or None when one is already active."""
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.learning_focus
                 (month, topic, topic_key, category, outcome, plan_if, plan_then, why, habit_tag)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT ((TRUE)) WHERE status = 'active' DO NOTHING RETURNING id""",
            (month, f["topic"], f["topic_key"], f["category"], f["outcome"], f["plan_if"], f["plan_then"],
             f["why"], f["habit_tag"])).fetchone()
        conn.commit()
    return get_focus(row[0]) if row else None


def update_focus(focus_id: int, fields: dict) -> bool:
    allowed = {k: v for k, v in fields.items() if k in {"topic", "topic_key", "category", "outcome", "plan_if",
                                                         "plan_then", "why"}}
    if not allowed:
        return False
    assignments = ", ".join(f"{k}=%s" for k in allowed)
    with database.connect() as conn:
        n = conn.execute(f"UPDATE journal.learning_focus SET {assignments}, updated_at=NOW() "
                         "WHERE id=%s AND status='active'", [*allowed.values(), focus_id]).rowcount
        conn.commit()
        return n > 0


def close_focus(focus_id: int, result: str, next_step: str) -> bool:
    with database.connect() as conn:
        n = conn.execute(
            """UPDATE journal.learning_focus SET status='closed', result=%s, next_step=%s, closed_at=NOW(),
                      updated_at=NOW() WHERE id=%s AND status='active'""", (result, next_step, focus_id)).rowcount
        conn.commit()
        return n > 0


def list_studies(topic_key: str | None = None) -> list[dict]:
    where, params = ("WHERE topic_key=%s", (topic_key,)) if topic_key else ("", ())
    return _rows(f"""SELECT id, topic_key, citation, url, finding, retrieved_on::text AS retrieved_on
                     FROM journal.learning_studies {where} ORDER BY created_at DESC, id DESC""", params)


def add_study(topic_key: str, citation: str, url: str, finding: str, retrieved_on: date) -> int | None:
    """The new id, or None when that link is already on this topic's shelf."""
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.learning_studies (topic_key, citation, url, finding, retrieved_on)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (topic_key, url) DO NOTHING RETURNING id""",
            (topic_key, citation, url, finding, retrieved_on)).fetchone()
        conn.commit()
        return row[0] if row else None


def delete_study(study_id: int) -> bool:
    with database.connect() as conn:
        n = conn.execute("DELETE FROM journal.learning_studies WHERE id=%s", (study_id,)).rowcount
        conn.commit()
        return n > 0
