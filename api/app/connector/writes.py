"""What the Claude connector may write, and nothing else.

Two kinds of write, both small and fixed:
- capture: one learning session (minutes) for today or the last week. It is undoable.
- propose: a study, a focus or a quest goes to the inbox and waits for the owner.

Not here, on purpose: closing a focus (the result is the owner's judgement), the review reflection and
recall (the owner's own words), journal notes, habits other than learning, and any edit or delete of
existing data. Every call is audited, rate-limited and idempotent when given a request id.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .. import db
from ..bot import store
from ..health import quality
from ..journal import learning, proposals, quests, repo

RATE_PER_HOUR = 60
MAX_BACK_DAYS = 7
MAX_MINUTES = 600


class Refused(Exception):
    """A write that was not made; the message is safe to show to the model and the owner."""


def _scalar(sql: str, params=()):
    with db.connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _audit(tool: str, client_id: str | None, summary: str, args: dict, outcome: str,
           ref_kind: str | None = None, ref_id: int | None = None, key: str | None = None) -> int:
    with db.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.connector_audit (client_id, tool, summary, args, outcome, ref_kind, ref_id,
                                                     idempotency_key)
               VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING id""",
            (client_id, tool, summary[:300], json.dumps(args), outcome, ref_kind, ref_id, key)).fetchone()
        conn.commit()
        return row[0]


def _duplicate(tool: str, key: str | None) -> dict | None:
    if not key:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT id, summary FROM journal.connector_audit WHERE tool=%s AND idempotency_key=%s "
                           "AND outcome='ok'", (tool, key)).fetchone()
    return {"duplicate": True, "audit_id": row[0], "summary": row[1]} if row else None


def _guard(tool: str, client_id: str | None, args: dict) -> None:
    recent = _scalar("SELECT COUNT(*) FROM journal.connector_audit WHERE outcome='ok' "
                     "AND at > NOW() - INTERVAL '1 hour'")
    if recent >= RATE_PER_HOUR:
        _audit(tool, client_id, "Refused: write limit reached for this hour", args, "refused")
        raise Refused(f"Write limit reached ({RATE_PER_HOUR} an hour). Try again later.")


def _key(request_id: str | None) -> str | None:
    key = (request_id or "").strip()
    return key[:80] or None


def log_learning_session(client_id: str | None, minutes: float, day: str | None = None,
                         request_id: str | None = None) -> dict:
    args = {"minutes": minutes, "date": day, "request_id": request_id}
    today = quality.today()
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        raise Refused("Minutes must be a number.") from None
    if not 1 <= value <= MAX_MINUTES:
        raise Refused(f"Minutes must be between 1 and {MAX_MINUTES}.")
    try:
        when = today if not day else date.fromisoformat(day)
    except ValueError:
        raise Refused("Use a date like 2026-10-15.") from None
    if when > today:
        raise Refused("That day has not happened yet.")
    if when < today - timedelta(days=MAX_BACK_DAYS):
        raise Refused(f"Only the last {MAX_BACK_DAYS} days can be logged this way.")
    key = _key(request_id)
    if (dup := _duplicate("lifey_log_learning_session", key)):
        return {"logged": False, **dup}
    _guard("lifey_log_learning_session", client_id, args)

    learning.ensure_habit()
    log_id = store.log_activity(date_str=when.isoformat(), category="unholy_habit", tag=learning.HABIT_TAG,
                                note="", value=value)
    shown = f"{value:g}"
    audit_id = _audit("lifey_log_learning_session", client_id,
                      f"Logged {shown} minutes of learning on {when.isoformat()}", {**args, "date": when.isoformat()},
                      "ok", "activity_log", log_id, key)
    return {"logged": True, "date": when.isoformat(), "minutes": value, "audit_id": audit_id,
            "undo": "Settings, Connector activity"}


def _propose(tool: str, client_id: str | None, kind: str, payload: dict, why: str, summary: str,
             args: dict, request_id: str | None) -> dict:
    key = _key(request_id)
    if (dup := _duplicate(tool, key)):
        return {"proposed": False, **dup}
    _guard(tool, client_id, args)
    if proposals.pending_count() >= proposals.MAX_PENDING:
        _audit(tool, client_id, "Refused: the inbox is full", args, "refused")
        raise Refused("The inbox already has 20 suggestions waiting. The owner needs to clear some first.")
    why = " ".join((why or "").split())[:300]
    pid = proposals.add(kind, payload, why)
    audit_id = _audit(tool, client_id, summary, args, "ok", "proposal", pid, key)
    return {"proposed": True, "proposal_id": pid, "audit_id": audit_id,
            "next": "Waiting for the owner to accept it in Lifey. It has not been applied."}


def propose_study(client_id: str | None, citation: str, url: str, finding: str, why: str = "",
                  request_id: str | None = None) -> dict:
    args = {"citation": citation, "url": url, "finding": finding, "why": why}
    study = learning.validate_study(citation, url, finding)
    active = repo.active_focus()
    if active is None:
        raise Refused("No learning focus is set, so there is no topic to attach a study to.")
    key = active["topic_key"]
    if any(s["url"] == study["url"] for s in repo.list_studies(key)) or proposals.has_pending_study(key, study["url"]):
        return {"proposed": False, "duplicate": True, "next": "That link is already on the shelf or in the inbox."}
    return _propose("lifey_propose_study", client_id, "study", {"topic_key": key, **study}, why,
                    f"Suggested a study: {study['citation'][:120]}", args, request_id)


def propose_focus(client_id: str | None, topic: str, category: str, outcome: str, plan_if: str = "",
                  plan_then: str = "", why: str = "", request_id: str | None = None) -> dict:
    args = {"topic": topic, "category": category, "outcome": outcome, "plan_if": plan_if, "plan_then": plan_then,
            "why": why}
    try:
        clean = learning.validate_focus({"topic": topic, "category": category, "outcome": outcome,
                                         "plan_if": plan_if, "plan_then": plan_then, "why": ""})
    except ValueError as exc:
        raise Refused(str(exc)) from exc
    return _propose("lifey_propose_focus", client_id, "focus", clean, why,
                    f"Suggested a focus: {clean['topic']}", args, request_id)


def propose_quest(client_id: str | None, kind: str, target: int, params: dict | None = None,
                  week: str = "next", request_id: str | None = None) -> dict:
    args = {"kind": kind, "target": target, "params": params or {}, "week": week}
    if week not in ("this", "next"):
        raise Refused("week must be 'this' or 'next'.")
    monday = quests.monday(quality.today()) + timedelta(days=0 if week == "this" else 7)
    try:
        clean = quests.validate(kind, int(target), params or {}, quests.habit_tags())
    except (ValueError, TypeError) as exc:
        raise Refused(str(exc)) from exc
    label = quests.label(kind, int(target), clean, quests.habit_tags())
    payload = {"week_start": monday.isoformat(), "kind": kind, "target": int(target), "params": clean}
    return _propose("lifey_propose_quest", client_id, "quest", payload, "",
                    f"Suggested a quest for the week of {monday.isoformat()}: {label}", args, request_id)
