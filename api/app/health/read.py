"""Read side: turns stored daily metrics into the Today payload."""
from __future__ import annotations

from datetime import timedelta

from psycopg import Connection

from ..models import Today
from ..readiness import build_metric, readiness

DAYS = 28

# metric key -> (column, label, unit, provenance, higher_is_better)
METRICS = [
    ("hrv", "hrv_last_night", "HRV, overnight", "ms", "estimate", True),
    ("sleep", "sleep_score", "Sleep score", "pts", "score", True),
    ("rhr", "resting_hr", "Resting heart rate", "bpm", "measured", False),
    ("steps", "steps", "Steps", "", "measured", True),
    ("spo2", "spo2_avg", "Blood oxygen, daily average", "%", "measured", True),
]


def today_from_db(conn: Connection) -> Today | None:
    head = conn.execute("SELECT max(date), max(synced_at) FROM health.daily_metrics").fetchone()
    anchor, synced_at = head
    if anchor is None:
        return None
    start = anchor - timedelta(days=DAYS - 1)
    columns = ", ".join(c for _, c, *_ in METRICS)
    rows = {r[0]: r for r in conn.execute(
        f"SELECT date, {columns}, metric_sources FROM health.daily_metrics WHERE date BETWEEN %s AND %s",
        (start, anchor)).fetchall()}

    metrics = []
    for i, (key, column, label, unit, provenance, higher) in enumerate(METRICS, start=1):
        series = []
        for d in range(DAYS):
            row = rows.get(start + timedelta(days=d))
            series.append(None if row is None or row[i] is None else float(row[i]))
        sources = rows[anchor][len(METRICS) + 1] or {}
        status = (sources.get(column) or {}).get("status")
        metrics.append(build_metric(key, label, unit, series, provenance, higher, source_status=status))

    verdict, reasons = readiness(metrics)
    return Today(date=anchor.isoformat(), source="garmin",
                 synced_at=synced_at.isoformat(timespec="minutes") if synced_at else None,
                 readiness=verdict, metrics=metrics, reasons=reasons)


def last_sync(conn: Connection) -> dict | None:
    row = conn.execute(
        "SELECT id, started_at, finished_at, status, details FROM health.sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "started_at": row[1].isoformat(),
            "finished_at": row[2].isoformat() if row[2] else None, "status": row[3], "details": row[4]}
