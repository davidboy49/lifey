"""Keep Lifey current from the running vidhealth database. Temporary bridge.

    python -m app.health.follow_vidhealth [--days 7]

Reads the old database through a READ-ONLY transaction (it cannot write
there), takes the last N days of source payloads, and replays them through the
same merge and parse rules as a live sync. Idempotent: payloads are
de-duplicated by hash, so running it every half hour is cheap and safe.

Why this exists: the old sync, bot, dashboard and MCP server still depend on
the old database, so it remains the only Garmin client until those consumers
move to Lifey. Lifey never contacts Garmin while this bridge is in use.

Env: OLD_DATABASE_URL (vidhealth), DATABASE_URL (Lifey).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

import psycopg

from .. import db
from . import quality
from . import journal_import
from .import_vidhealth import _iso, _json, build_history, import_history


def read_old(conn: psycopg.Connection, days: int):
    """Payload and daily rows for the last `days` days from a vidhealth database."""
    since = (quality.today() - timedelta(days=days)).isoformat()
    payload_rows = []
    for rid, day, received, payload in conn.execute(
            """SELECT id, date, received_at::text, payload::text FROM source_payloads
               WHERE date >= %s ORDER BY date, received_at, id""", (since,)):
        body = _json(payload)
        if body is not None:
            payload_rows.append((day, _iso(received), int(rid), body))
    daily_rows = [(day, raw, synced) for day, raw, synced in conn.execute(
        "SELECT date, raw_json, synced_at::text FROM daily_metrics WHERE date >= %s", (since,))]
    return payload_rows, daily_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    if not 1 <= args.days <= 400:
        raise SystemExit("--days must be between 1 and 400")
    old_url = os.environ.get("OLD_DATABASE_URL")
    if not old_url:
        raise SystemExit("OLD_DATABASE_URL is not set")

    with psycopg.connect(old_url, connect_timeout=15) as old:
        old.read_only = True  # the server itself refuses any write on this session
        payload_rows, daily_rows = read_old(old, args.days)
        journal = journal_import.read_live(old)
        old.rollback()
    history = build_history(payload_rows, daily_rows)
    history.journal = journal
    with db.connect() as conn:
        result = import_history(conn, history)
    result.pop("skipped_no_payload", None)
    print(json.dumps(result))
    return 0 if not result["days_failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
