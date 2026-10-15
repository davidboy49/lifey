"""Suggestions from the Claude connector that wait for the owner.

A study, a monthly focus or a weekly quest is a commitment or a claim, so the connector can only
propose it. Accepting runs the same validated handler the web page uses; rejecting changes nothing.
The connector never reads a proposal back or decides one.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .. import db as database
from . import learning, quests, repo

MAX_PENDING = 20


class Conflict(Exception):
    """The proposal cannot be applied right now; the message says why in plain words."""


def _rows(sql: str, params=()) -> list[dict]:
    with database.connect() as conn:
        cur = conn.execute(sql, params)
        names = [c.name for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def pending_count() -> int:
    return _rows("SELECT COUNT(*) AS n FROM journal.proposals WHERE status='pending'")[0]["n"]


def add(kind: str, payload: dict, why: str = "") -> int:
    with database.connect() as conn:
        row = conn.execute("INSERT INTO journal.proposals (kind, payload, why) VALUES (%s,%s::jsonb,%s) RETURNING id",
                           (kind, json.dumps(payload), why)).fetchone()
        conn.commit()
        return row[0]


def get(proposal_id: int) -> dict | None:
    rows = _rows("SELECT id, kind, payload, why, status, created_at FROM journal.proposals WHERE id=%s",
                 (proposal_id,))
    return rows[0] if rows else None


def has_pending_study(topic_key: str, url: str) -> bool:
    return bool(_rows("SELECT 1 FROM journal.proposals WHERE kind='study' AND status='pending' "
                      "AND payload->>'topic_key'=%s AND payload->>'url'=%s", (topic_key, url)))


def _decide(proposal_id: int, status: str) -> bool:
    with database.connect() as conn:
        n = conn.execute("UPDATE journal.proposals SET status=%s, decided_at=NOW() WHERE id=%s AND status='pending'",
                         (status, proposal_id)).rowcount
        conn.commit()
        return n > 0


def reject(proposal_id: int) -> bool:
    return _decide(proposal_id, "rejected")


def pending(today: date) -> list[dict]:
    """Pending proposals with what the owner needs to decide, and what accepting would replace."""
    out = []
    for p in _rows("SELECT id, kind, payload, why, created_at FROM journal.proposals WHERE status='pending' "
                   "ORDER BY created_at, id"):
        item = {"id": p["id"], "kind": p["kind"], "why": p["why"], "created_at": p["created_at"],
                "payload": p["payload"], "replaces": None, "blocked": None}
        if p["kind"] == "focus":
            active = repo.active_focus()
            if active:
                item["blocked"] = f"You already have a focus: {active['topic']}. Close it first."
        elif p["kind"] == "quest":
            week = date.fromisoformat(p["payload"]["week_start"])
            current = quests.monday(today)
            if week not in (current, current + timedelta(days=7)):
                item["blocked"] = "That week has passed."
            else:
                existing = repo.get_quest(week)
                if existing:
                    item["replaces"] = quests.label(existing["kind"], existing["target"], existing["params"],
                                                    quests.habit_tags())
            item["label"] = quests.label(p["payload"]["kind"], p["payload"]["target"], p["payload"]["params"],
                                         quests.habit_tags())
        out.append(item)
    return out


def accept(proposal_id: int, today: date) -> dict:
    """Apply a pending proposal through the normal validated path, then mark it accepted."""
    p = get(proposal_id)
    if p is None or p["status"] != "pending":
        raise LookupError("No pending proposal with that id.")
    data = p["payload"]
    result: dict
    if p["kind"] == "study":
        new_id = repo.add_study(data["topic_key"], data["citation"], data["url"], data["finding"],
                                p["created_at"].date())
        result = {"applied": "study", "duplicate": new_id is None}
    elif p["kind"] == "focus":
        fields = learning.validate_focus(data)
        fields["habit_tag"] = learning.ensure_habit()
        created = repo.create_focus(learning.month_start(today), fields)
        if created is None:
            raise Conflict("You already have a focus. Close it before accepting another.")
        result = {"applied": "focus", "id": created["id"]}
    else:
        week = date.fromisoformat(data["week_start"])
        current = quests.monday(today)
        if week not in (current, current + timedelta(days=7)):
            raise Conflict("That week has passed, so the quest can no longer be set.")
        saved = quests.save(week, data["kind"], data["target"], data["params"])
        result = {"applied": "quest", **saved}
    _decide(proposal_id, "accepted")
    return result
