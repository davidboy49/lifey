"""Garmin sync entry points for the bot (runs in worker threads)."""
from __future__ import annotations

from .. import db
from ..health import sync


def smart_sync(days: int = 3) -> dict:
    from . import anomaly  # needs pandas; imported lazily

    with db.connect() as conn:
        return sync.run_sync(conn, sync.window(int(days)), force=True,
                             after_day=anomaly.dispatch_alerts_if_needed)
