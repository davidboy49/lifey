"""Garmin sync: fetch rolling days, persist atomically, report honestly.

    python -m app.health.sync smart 3
    python -m app.health.sync backfill 30 --force

Exit status is non-zero for anything other than a fully successful run, so a
scheduler or container restart policy surfaces partial failures.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from psycopg import Connection
from psycopg.types.json import Jsonb

from .. import db
from . import quality, store

SYNC_LOCK_KEY = 8410327755203

# source -> (Garmin client method, key used for its error in the fetched dict)
ENDPOINTS: list[tuple[str, str, str]] = [
    ("hrv", "get_hrv_data", "hrv_error"),
    ("sleep", "get_sleep_data", "sleep_error"),
    ("heart_rate", "get_heart_rates", "hr_error"),
    ("body_battery", "get_body_battery", "body_battery_error"),
    ("stress", "get_all_day_stress", "stress_error"),
    ("steps", "get_steps_data", "steps_error"),
    ("training_readiness", "get_morning_training_readiness", "readiness_error"),
    ("summary", "get_stats", "summary_error"),
    ("pulse_ox", "get_spo2_data", "pulse_ox_error"),
    ("respiration", "get_respiration_data", "respiration_error"),
]


def get_api():
    from garminconnect import Garmin  # imported lazily: only the sync job needs it

    email, password = os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        raise ValueError("GARMIN_EMAIL and GARMIN_PASSWORD must be set")
    tokens = Path(os.environ.get("GARMIN_TOKEN_DIR", ".garmin_tokens"))
    tokens.mkdir(parents=True, exist_ok=True)
    api = Garmin(email, password)
    api.login(str(tokens))  # cached tokens avoid 429 rate limits
    return api


def fetch_day(api, target_date: str) -> dict:
    """Fetch every endpoint independently. One failing endpoint never loses the rest."""
    result: dict = {"date": target_date}
    for source, method, error_key in ENDPOINTS:
        try:
            value = getattr(api, method)(target_date)
            if value is not None:
                result[source] = value
        except Exception as exc:  # noqa: BLE001 - recorded as a status, not raised
            result[error_key] = str(exc)
    try:
        value = api.get_activities_by_date(target_date, target_date)
        if value is not None:
            result["activities"] = value
    except Exception as exc:  # noqa: BLE001
        try:
            value = api.get_activities_fordate(target_date)
            if value is not None:
                result["activities"] = value
        except Exception:  # noqa: BLE001
            result["activities_error"] = str(exc)
    return result


@contextmanager
def sync_job(conn: Connection):
    """One sync at a time across the CLI, worker and any API trigger."""
    locked = conn.execute("SELECT pg_try_advisory_lock(%s)", (SYNC_LOCK_KEY,)).fetchone()[0]
    if not locked:
        raise RuntimeError("Another Garmin sync is already running.")
    try:
        run_id = conn.execute("INSERT INTO health.sync_runs(status) VALUES ('running') RETURNING id").fetchone()[0]
        conn.commit()
        yield run_id
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_KEY,))
        conn.commit()


def _finish(conn: Connection, run_id: int, status: str, details: dict) -> None:
    conn.execute("UPDATE health.sync_runs SET status=%s, details=%s, finished_at=NOW() WHERE id=%s",
                 (status, Jsonb(details), run_id))
    conn.commit()


def run_sync(conn: Connection, dates: list[str], *, api=None, force: bool = True,
             pause: float = 1.0, after_day=None) -> dict:
    """Sync the given ISO dates. `api` is injectable so tests need no Garmin account."""
    with sync_job(conn) as run_id:
        synced, failed, skipped, warnings = [], [], [], {}
        try:
            api = api or get_api()
            for index, ds in enumerate(dates):
                if not force and index >= 3 and _already_complete(conn, ds):
                    skipped.append(ds)
                    continue
                try:
                    data = fetch_day(api, ds)
                    issues = {quality.ERROR_NAMES.get(k, k.removesuffix("_error")): "fetch_failed"
                              for k in data if k.endswith("_error")}
                    states = quality.merge_sources({}, data)["_sources"]
                    issues.update({k: v["status"] for k, v in states.items() if v["status"] == "parse_failed"})
                    if issues:
                        warnings[ds] = issues
                    if not any(s["status"] == "available" for s in states.values()):
                        failed.append(ds)  # nothing usable: leave earlier data untouched
                        continue
                    store.save_day(conn, ds, data)
                    conn.commit()
                    synced.append(ds)
                    if after_day is not None:
                        try:
                            after_day(ds)
                        except Exception:  # noqa: BLE001 - alerts must never fail a sync
                            warnings.setdefault(ds, {})["alerts"] = "Alert refresh failed"
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    failed.append(ds)
                    # Keep credentials and response bodies out of logs and the run record.
                    warnings.setdefault(ds, {})["persistence"] = "Fetch or persistence failed; inspect server logs"
                if index < len(dates) - 1 and pause:
                    time.sleep(pause)
            status = "failed" if not synced and not skipped else "partial" if failed or warnings else "success"
            result = {"status": status, "synced_dates": synced, "failed_dates": failed,
                      "skipped_dates": skipped, "total_requested": len(dates), "warnings": warnings}
            _finish(conn, run_id, status, result)
            return result
        except Exception:
            conn.rollback()
            _finish(conn, run_id, "failed", {"error": "Sync could not complete"})
            raise


def _already_complete(conn: Connection, ds: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM health.endpoint_state WHERE date=%s AND status='available'", (ds,)).fetchone()
    return row[0] >= 3


def window(days: int) -> list[str]:
    return [(quality.today() - timedelta(days=i)).isoformat() for i in range(days)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["today", "smart", "backfill"], default="smart")
    parser.add_argument("days", nargs="?", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "backfill":
            days, force = args.days or 30, args.force
            if not 1 <= days <= 3660:
                raise ValueError("days must be between 1 and 3660")
        else:
            days, force = args.days or 3, True
            if not 1 <= days <= 366:
                raise ValueError("days must be between 1 and 366")
        try:
            from ..bot import anomaly  # optional: needs the bot extras (pandas)
            after_day = anomaly.dispatch_alerts_if_needed
        except ImportError:
            after_day = None
        with db.connect() as conn:
            result = run_sync(conn, window(days), force=force, after_day=after_day)
        print(json.dumps(result))
        return 0 if result["status"] == "success" else 1
    except Exception:  # noqa: BLE001
        print("Sync failed. Check credentials, connection, and job status.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
