"""Is the off-box backup working, and does it need the owner's attention?

deploy/backup.sh writes a row to journal.backup_runs for every attempt. This
reads them back and turns them into a state the web and the bot can show.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import db

STALE_AFTER = timedelta(hours=36)     # a nightly job that hasn't succeeded in a day and a half
AUTH_HINT = re.compile(r"invalid_grant|token|oauth|401|unauthori[sz]ed|expired|reauth|403", re.I)


def _row(r) -> dict:
    return {"id": r[0], "started_at": r[1], "finished_at": r[2], "ok": r[3], "bytes": r[4], "files": r[5],
            "destination": r[6], "detail": r[7]}


def status(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    with db.connect() as conn:
        last = conn.execute(
            "SELECT id, started_at, finished_at, ok, bytes, files, destination, detail "
            "FROM journal.backup_runs ORDER BY id DESC LIMIT 1").fetchone()
        last_ok = conn.execute(
            "SELECT id, started_at, finished_at, ok, bytes, files, destination, detail "
            "FROM journal.backup_runs WHERE ok ORDER BY id DESC LIMIT 1").fetchone()
        recent = conn.execute(
            "SELECT id, started_at, finished_at, ok, bytes, files, destination, detail "
            "FROM journal.backup_runs ORDER BY id DESC LIMIT 7").fetchall()
    out = {"state": "never", "needs_attention": True, "headline": "No backup has run yet.", "hint": None,
           "last_ok_at": None, "last_ok_bytes": None, "last_ok_files": None, "destination": None, "recent": []}
    if not last:
        return out
    out["recent"] = [{"started_at": r[1].isoformat(), "ok": r[3], "bytes": r[4]} for r in recent]
    ok = _row(last_ok) if last_ok else None
    if ok:
        out.update(last_ok_at=(ok["finished_at"] or ok["started_at"]).isoformat(), last_ok_bytes=ok["bytes"],
                   last_ok_files=ok["files"], destination=ok["destination"])
    latest = _row(last)
    age_ok = (now - (ok["finished_at"] or ok["started_at"])) if ok else None

    if latest["ok"] is False:
        out["state"], out["needs_attention"] = "failed", True
        detail = latest["detail"] or ""
        if AUTH_HINT.search(detail):
            out["headline"] = "Google Drive needs you to sign in again."
            out["hint"] = ("Run `rclone config reconnect lifeydrive:` on your PC, then tell Claude it's done "
                           "so the new sign-in gets copied to the server.")
        else:
            out["headline"] = "The last backup failed."
            out["hint"] = detail[:240] or "Check the backup log on the server."
    elif ok is None or (age_ok is not None and age_ok > STALE_AFTER):
        out["state"], out["needs_attention"] = "stale", True
        out["headline"] = "No successful backup in over a day and a half."
        out["hint"] = "The nightly job may not be running. Check the backup timer on the server."
    elif latest["ok"] is None:
        out["state"], out["needs_attention"] = "running", False
        out["headline"] = "A backup is running."
    else:
        out["state"], out["needs_attention"] = "ok", False
        out["headline"] = "Backups are up to date."
    return out
