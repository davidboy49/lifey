"""Model registry helpers: register an artifact, promote it, keep the last 3 files.

Files are named `<target>_h<horizon>_<YYYY-MM-DD>.joblib` (see ml/README.md). Promotion is a
decision made with `report.should_promote`; this module only records and enforces it.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

KEEP = 3
_NAME = re.compile(r"^(?P<stem>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.joblib$")


def register(conn, *, model_name: str, model_version: str, kind: str, target: str, horizon_days: int,
             path: str | None, trained_through: date | None = None, cv_mae: float | None = None,
             last30_mae: float | None = None, naive_last30_mae: float | None = None) -> None:
    conn.execute(
        """INSERT INTO ml.model_registry (model_name, model_version, kind, target, horizon_days, path,
               trained_through, cv_mae, last30_mae, naive_last30_mae, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'candidate')
           ON CONFLICT (model_name, model_version) DO UPDATE SET
               path=excluded.path, cv_mae=excluded.cv_mae, last30_mae=excluded.last30_mae,
               naive_last30_mae=excluded.naive_last30_mae""",
        (model_name, model_version, kind, target, horizon_days, path, trained_through,
         cv_mae, last30_mae, naive_last30_mae))


def promote(conn, model_name: str, model_version: str) -> None:
    """Make this artifact the promoted one for its target and horizon; retire the previous."""
    target, horizon = conn.execute(
        "SELECT target, horizon_days FROM ml.model_registry WHERE model_name=%s AND model_version=%s",
        (model_name, model_version)).fetchone()
    conn.execute(
        """UPDATE ml.model_registry SET status='retired'
           WHERE status='promoted' AND target=%s AND horizon_days=%s""", (target, horizon))
    conn.execute(
        """UPDATE ml.model_registry SET status='promoted', promoted_at=NOW()
           WHERE model_name=%s AND model_version=%s""", (model_name, model_version))


def prune_files(directory: Path, stem: str, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest `keep` dated artifacts for `stem`. Returns what was removed."""
    dated = []
    for p in directory.glob(f"{stem}_*.joblib"):
        m = _NAME.match(p.name)
        if m and m["stem"] == stem:
            dated.append((m["date"], p))
    dated.sort(reverse=True)
    removed = [p for _, p in dated[keep:]]
    for p in removed:
        p.unlink()
    return removed
