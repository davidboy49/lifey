"""The inbox of suggestions from Claude, and the trail of what the connector wrote."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..auth.deps import current_user
from ..bot import store
from ..health import quality
from . import proposals

router = APIRouter(prefix="/api", tags=["connector"], dependencies=[Depends(current_user)])


@router.get("/proposals")
def inbox() -> dict:
    return {"proposals": proposals.pending(quality.today())}


@router.post("/proposals/{proposal_id}/accept")
def accept(proposal_id: int) -> dict:
    try:
        return proposals.accept(proposal_id, quality.today())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except proposals.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: int) -> dict:
    if not proposals.reject(proposal_id):
        raise HTTPException(404, "No pending proposal with that id.")
    return {"rejected": True}


def _activity(limit: int = 40) -> list[dict]:
    with db.connect() as conn:
        cur = conn.execute(
            """SELECT a.id, a.at, a.client_id, a.tool, a.summary, a.outcome, a.ref_kind, a.ref_id, a.undone_at,
                      (a.ref_kind = 'activity_log' AND a.undone_at IS NULL
                         AND EXISTS (SELECT 1 FROM journal.activity_logs l WHERE l.id = a.ref_id)) AS log_alive,
                      (SELECT p.status FROM journal.proposals p WHERE a.ref_kind = 'proposal' AND p.id = a.ref_id)
                        AS proposal_status
               FROM journal.connector_audit a ORDER BY a.at DESC, a.id DESC LIMIT %s""", (limit,))
        names = [c.name for c in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
    for r in rows:
        r["can_undo"] = bool(r["log_alive"]) or r["proposal_status"] == "pending"
        del r["log_alive"]
    return rows


@router.get("/connector/activity")
def activity() -> dict:
    return {"activity": _activity()}


@router.post("/connector/activity/{audit_id}/undo")
def undo(audit_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT ref_kind, ref_id, undone_at FROM journal.connector_audit WHERE id=%s "
                           "AND outcome='ok'", (audit_id,)).fetchone()
    if row is None or row[2] is not None:
        raise HTTPException(404, "Nothing to undo for that entry.")
    kind, ref = row[0], row[1]
    if kind == "activity_log":
        done = store.delete_activity_log(ref)
    elif kind == "proposal":
        done = proposals.reject(ref)
    else:
        done = False
    if not done:
        raise HTTPException(409, "It has already been removed or decided.")
    with db.connect() as conn:
        conn.execute("UPDATE journal.connector_audit SET undone_at=NOW() WHERE id=%s", (audit_id,))
        conn.commit()
    return {"undone": True}
