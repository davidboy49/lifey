"""Data tables: browse and export the datasets Lifey keeps.

Read-only. Values are returned as stored: a missing value is null, never zero,
and every daily row says whether any of its sources failed.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from . import db
from .auth.deps import current_user
from .health import quality

router = APIRouter(prefix="/api/data", tags=["data"], dependencies=[Depends(current_user)])

EXPORT_LIMIT = 50_000


def _tz() -> str:
    return str(quality.user_timezone())


# id -> (label, select, order, columns[(key, label, kind)])
# `kind` is a display hint for the table: text, number, date, time, chip.
DATASETS: dict[str, dict] = {
    "daily_metrics": {
        "label": "Daily metrics",
        "sql": """SELECT d.date::text AS date, d.hrv_last_night, d.hrv_weekly_avg, d.hrv_status, d.sleep_score,
                         ROUND((d.sleep_duration / 3600.0)::numeric, 2) AS sleep_hours, d.resting_hr, d.min_hr, d.max_hr,
                         d.bb_max, d.bb_min, d.stress_avg, d.steps, d.floors, d.training_readiness,
                         d.spo2_avg, d.spo2_min, d.respiration_avg, d.workout_type,
                         CASE WHEN EXISTS (SELECT 1 FROM health.endpoint_state e WHERE e.date = d.date
                                           AND e.status IN ('fetch_failed','parse_failed'))
                              THEN 'partial' ELSE 'complete' END AS source,
                         d.synced_at
                  FROM health.daily_metrics d""",
        "order": "d.date",
        "count": "SELECT count(*) FROM health.daily_metrics",
        "columns": [("date", "Date", "date"), ("hrv_last_night", "HRV (ms)", "number"), ("hrv_weekly_avg", "HRV week avg", "number"),
                    ("hrv_status", "HRV status", "text"), ("sleep_score", "Sleep score", "number"),
                    ("sleep_hours", "Sleep (h)", "number"), ("resting_hr", "Resting HR", "number"),
                    ("min_hr", "Min HR", "number"), ("max_hr", "Max HR", "number"), ("bb_max", "Body battery max", "number"),
                    ("bb_min", "Body battery min", "number"), ("stress_avg", "Stress avg", "number"),
                    ("steps", "Steps", "number"), ("floors", "Floors", "number"),
                    ("training_readiness", "Readiness", "number"), ("spo2_avg", "SpO2 avg", "number"),
                    ("spo2_min", "SpO2 min", "number"), ("respiration_avg", "Respiration", "number"),
                    ("workout_type", "Workout", "text"), ("source", "Sources", "chip"), ("synced_at", "Synced", "time")],
        "default_hidden": ["hrv_weekly_avg", "min_hr", "max_hr", "bb_min", "floors", "spo2_min", "respiration_avg", "synced_at"],
    },
    "activities": {
        "label": "Activities",
        "sql": """SELECT date::text AS date, to_char(started_local, 'HH24:MI') AS start, name, type,
                         ROUND((duration_seconds / 60.0)::numeric, 1) AS minutes, ROUND((distance_meters / 1000.0)::numeric, 2) AS km,
                         calories, avg_hr, max_hr, aerobic_training_effect, anaerobic_training_effect, steps
                  FROM health.activities""",
        "order": "date, started_local",
        "count": "SELECT count(*) FROM health.activities",
        "columns": [("date", "Date", "date"), ("start", "Start", "text"), ("name", "Name", "text"), ("type", "Type", "text"),
                    ("minutes", "Minutes", "number"), ("km", "Distance (km)", "number"), ("calories", "Calories", "number"),
                    ("avg_hr", "Avg HR", "number"), ("max_hr", "Max HR", "number"),
                    ("aerobic_training_effect", "Aerobic TE", "number"), ("anaerobic_training_effect", "Anaerobic TE", "number"),
                    ("steps", "Steps", "number")],
        "default_hidden": ["anaerobic_training_effect", "steps"],
    },
    "journal": {
        "label": "Journal",
        "sql": """SELECT id, date::text AS date, occurred_at AS happened, category, tag, note, value,
                         ts AS saved_at, (ts::date > date) AS recalled, origin
                  FROM journal.activity_logs""",
        "order": "date, ts",
        "count": "SELECT count(*) FROM journal.activity_logs",
        "columns": [("id", "ID", "number"), ("date", "Date", "date"), ("happened", "Happened", "text"),
                    ("category", "Category", "text"), ("tag", "Tag", "text"), ("note", "Note", "text"),
                    ("value", "Value", "number"), ("saved_at", "Saved", "time"), ("recalled", "Recalled", "chip"),
                    ("origin", "Origin", "text")],
        "default_hidden": ["id", "origin"],
    },
    "habits": {
        "label": "Habits",
        "sql": """SELECT id, date::text AS date, tag AS habit, value AS units, note,
                         ts AS saved_at, (ts::date > date) AS recalled
                  FROM journal.activity_logs WHERE category = 'unholy_habit'""",
        "order": "date, ts",
        "count": "SELECT count(*) FROM journal.activity_logs WHERE category = 'unholy_habit'",
        "columns": [("id", "ID", "number"), ("date", "Date", "date"), ("habit", "Habit", "text"),
                    ("units", "Units", "number"), ("note", "Note", "text"), ("saved_at", "Saved", "time"),
                    ("recalled", "Recalled", "chip")],
        "default_hidden": ["id"],
    },
    "alerts": {
        "label": "Alerts",
        "sql": """SELECT id, date::text AS date, severity, alert_type, message, alert_state, delivered, ts
                  FROM journal.anomaly_alerts""",
        "order": "date, ts",
        "count": "SELECT count(*) FROM journal.anomaly_alerts",
        "columns": [("date", "Date", "date"), ("severity", "Severity", "text"), ("alert_type", "Type", "text"),
                    ("message", "Message", "text"), ("alert_state", "State", "text"), ("delivered", "Delivered", "chip"),
                    ("ts", "Raised", "time")],
        "default_hidden": [],
    },
    "sync_runs": {
        "label": "Sync runs",
        "sql": "SELECT id, started_at, finished_at, status, details FROM health.sync_runs",
        "order": "id",
        "count": "SELECT count(*) FROM health.sync_runs",
        "columns": [("id", "Run", "number"), ("started_at", "Started", "time"), ("finished_at", "Finished", "time"),
                    ("status", "Status", "chip"), ("details", "Details", "text")],
        "default_hidden": [],
    },
}


def _dataset(name: str) -> dict:
    if name not in DATASETS:
        raise HTTPException(404, "Unknown dataset.")
    return DATASETS[name]


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if hasattr(v, "isoformat"):
        try:
            return v.astimezone(quality.user_timezone()).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, AttributeError):
            return v.isoformat()
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, default=str)
    return str(v)


def _fetch(ds: dict, order_desc: bool, limit: int | None, offset: int = 0) -> list[dict]:
    direction = "DESC" if order_desc else "ASC"
    order = ", ".join(f"{part.strip()} {direction}" for part in ds["order"].split(","))
    tail = "" if limit is None else f" LIMIT {int(limit)} OFFSET {int(offset)}"
    with db.connect() as conn:
        cur = conn.execute(f"{ds['sql']} ORDER BY {order}{tail}")
        names = [c.name for c in cur.description]
        return [{k: _jsonable(v) for k, v in zip(names, row)} for row in cur.fetchall()]


@router.get("")
def list_datasets() -> list[dict]:
    out = []
    with db.connect() as conn:
        for key, ds in DATASETS.items():
            out.append({"key": key, "label": ds["label"], "rows": conn.execute(ds["count"]).fetchone()[0]})
    return out


@router.get("/{name}")
def table(name: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
          order: str = Query("desc", pattern="^(asc|desc)$")) -> dict:
    ds = _dataset(name)
    with db.connect() as conn:
        total = conn.execute(ds["count"]).fetchone()[0]
    return {
        "key": name, "label": ds["label"], "total": total, "limit": limit, "offset": offset,
        "columns": [{"key": k, "label": lab, "kind": kind, "hidden": k in ds["default_hidden"]}
                    for k, lab, kind in ds["columns"]],
        "rows": _fetch(ds, order == "desc", limit, offset),
    }


def _safe_cell(v):
    """Stop spreadsheet formula injection: a note that starts with = + - @ is text, not a formula."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return "" if v is None else v


def csv_text(name: str, days: int | None = None) -> tuple[str, int]:
    """The dataset as CSV text, oldest first, and its row count.

    `days` keeps only the last N local days (today included); None keeps everything.
    Used by the web export and by the Telegram /export command.
    """
    ds = _dataset(name)
    rows = _fetch(ds, order_desc=False, limit=EXPORT_LIMIT)
    keys = [k for k, _, _ in ds["columns"]]
    if days is not None and "date" in keys:
        cutoff = (quality.today() - timedelta(days=days - 1)).isoformat()
        rows = [r for r in rows if str(r.get("date") or "")[:10] >= cutoff]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([lab for _, lab, _ in ds["columns"]])
    for row in rows:
        writer.writerow([_safe_cell(row.get(k)) for k in keys])
    return buf.getvalue(), len(rows)


@router.get("/{name}/export.csv")
def export_csv(name: str) -> Response:
    text, _ = csv_text(name)
    filename = f"lifey-{name}-{quality.today().isoformat()}.csv"
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})
