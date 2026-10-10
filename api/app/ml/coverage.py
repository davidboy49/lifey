"""Read-only data coverage report for health.daily_metrics.

    python -m app.ml.coverage [--days 90]

Answers: how many rows, what date range, which calendar days have no row at all,
and how complete each metric is. A missing day is reported, never filled.
Exit status is 1 when the table has fewer rows than --min-rows (default 90).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from .. import db
from ..health import quality

METRICS = [
    "hrv_last_night", "sleep_score", "sleep_duration", "resting_hr", "bb_max", "stress_avg",
    "steps", "training_readiness", "spo2_avg", "respiration_avg",
]


def build_report(conn, *, days: int = 90, today: date | None = None) -> dict:
    today = today or quality.today()
    rows = conn.execute("SELECT date FROM health.daily_metrics ORDER BY date").fetchall()
    have = {r[0] for r in rows}
    report: dict = {"rows": len(have), "as_of": today.isoformat()}
    if not have:
        return {**report, "first_date": None, "last_date": None, "missing_dates": [],
                "metrics": {}, "last_sync": None, "days_since_last_row": None}

    first, last = min(have), max(have)
    span = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    report.update(first_date=first.isoformat(), last_date=last.isoformat(),
                  missing_dates=[d.isoformat() for d in span if d not in have],
                  days_since_last_row=(today - last).days)

    window_start = today - timedelta(days=days - 1)
    window_rows = [d for d in have if d >= window_start]
    metrics = {}
    for name in METRICS:
        non_null = conn.execute(
            f"SELECT count(*) FROM health.daily_metrics WHERE date >= %s AND {name} IS NOT NULL",
            (window_start,)).fetchone()[0]
        metrics[name] = {"non_null": non_null, "of": days, "pct": round(100 * non_null / days, 1)}
    report["window_days"] = days
    report["window_rows"] = len(window_rows)
    report["metrics"] = metrics

    run = conn.execute(
        "SELECT started_at, finished_at, status FROM health.sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    report["last_sync"] = None if run is None else {
        "started_at": run[0].isoformat(), "finished_at": run[1].isoformat() if run[1] else None, "status": run[2]}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--min-rows", type=int, default=90)
    args = parser.parse_args(argv)
    with db.connect() as conn:
        report = build_report(conn, days=args.days)
    print(json.dumps(report, indent=2))
    return 0 if report["rows"] >= args.min_rows else 1


if __name__ == "__main__":
    sys.exit(main())
