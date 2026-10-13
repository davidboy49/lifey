"""Data layer for the Telegram bot, served from Lifey's tables.

The bot and its helper modules were written against vidhealth's `db` module and
its row shapes (TEXT dates, `raw_json` provenance, `timestamp` strings). This
module keeps those shapes so the logic can move over unchanged, while the data
lives in Lifey's typed schemas.

Functions open one short connection each; the bot calls them from threads.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd

from .. import db as database
from ..health import quality

ENDPOINTS = sorted(quality.SOURCES)
_DAILY_COLUMNS = [
    "hrv_last_night", "hrv_weekly_avg", "hrv_status", "sleep_score", "sleep_duration", "sleep_deep",
    "sleep_light", "sleep_rem", "sleep_awake", "resting_hr", "min_hr", "max_hr", "bb_max", "bb_min",
    "bb_charged", "bb_drained", "stress_avg", "stress_max", "steps", "floors", "training_readiness",
    "spo2_avg", "spo2_min", "respiration_avg", "respiration_min", "workout_type",
]


def _local(ts, fmt="%Y-%m-%d %H:%M:%S"):
    """Format a timestamptz in the user's zone. Done here, not with AT TIME ZONE,
    so we never depend on which zone names the database server knows."""
    return None if ts is None else ts.astimezone(quality.user_timezone()).strftime(fmt)


def _stamp(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["timestamp"] = _local(r.pop("ts"))
    return rows


def _rows(sql: str, params=()) -> list[dict]:
    with database.connect() as conn:
        cur = conn.execute(sql, params)
        names = [c.name for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def _iso_days_ago(days: int) -> str:
    return (quality.today() - timedelta(days=int(days))).isoformat()


# ---------- daily metrics ----------

def get_df(limit: int | None = 30) -> pd.DataFrame:
    """Daily metrics, oldest to newest, with vidhealth's column names.

    `raw_json` is rebuilt from Lifey's provenance so coaching can read
    `_sources`, `_metric_sources` and `_metric_issues` exactly as before."""
    limit_sql = "" if limit is None else "LIMIT %s"
    params = () if limit is None else (int(limit),)
    rows = _rows(f"""
        SELECT * FROM (
          SELECT d.date::text AS date, {', '.join('d.' + c for c in _DAILY_COLUMNS)},
                 d.metric_sources, d.metric_issues, d.synced_at,
                 (SELECT COALESCE(jsonb_object_agg(e.endpoint, jsonb_strip_nulls(jsonb_build_object(
                     'status', e.status, 'fetched_at', e.fetched_at, 'attempted_at', e.attempted_at,
                     'payload_hash', e.payload_hash, 'retained', e.retained))), '{{}}'::jsonb)
                    FROM health.endpoint_state e WHERE e.date = d.date) AS sources,
                 EXISTS (SELECT 1 FROM journal.activity_logs a WHERE a.date = d.date AND a.tag = 'alcohol')::int
                    AS alcohol_logged
          FROM health.daily_metrics d ORDER BY d.date DESC {limit_sql}
        ) recent ORDER BY date ASC""", params)
    if not rows:
        return pd.DataFrame(columns=["date", *_DAILY_COLUMNS, "alcohol_logged", "raw_json", "synced_at"])
    for r in rows:
        r["raw_json"] = json.dumps({"_sources": r.pop("sources"),
                                    "_metric_sources": r.pop("metric_sources"),
                                    "_metric_issues": r.pop("metric_issues")}, default=str)
        r["ai_summary"] = None
        r["sleep_apnea_flag"] = 0
    return pd.DataFrame(rows)


# ---------- journal ----------

_LOG_COLUMNS = "id, date::text AS date, ts, category, tag, note, value, occurred_at"


def log_activity(date_str: str, category: str, tag: str, note: str = "", value: float | None = None,
                 occurred_at: str | None = None) -> int:
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.activity_logs (date, category, tag, note, value, occurred_at)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (date_str, category, tag, note, value, occurred_at)).fetchone()
        conn.commit()
        return row[0]


def get_activity_logs(date_str: str | None = None, limit: int = 50) -> list[dict]:
    if date_str:
        return _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs WHERE date=%(d)s "
                            "ORDER BY ts DESC, id DESC LIMIT %(n)s", {"d": date_str, "n": limit}))
    return _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs "
                        "ORDER BY date DESC, ts DESC, id DESC LIMIT %(n)s", {"n": limit}))


def get_activity_log(log_id: int) -> dict | None:
    rows = _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs WHERE id=%(i)s", {"i": log_id}))
    return rows[0] if rows else None


def get_quit_logs() -> list[dict]:
    return _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs "
                        "WHERE category IN ('master','wellbeing') OR tag='master' ORDER BY date, ts, id"))


def get_quit_reasons() -> list[dict]:
    return _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs WHERE category='quit_reason' "
                        "ORDER BY ts, id"))


def get_training_logs(days: int = 60) -> list[dict]:
    return _stamp(_rows(f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs WHERE category='training' "
                        "AND date >= %(since)s ORDER BY date, ts", {"since": _iso_days_ago(days)}))


def delete_training_logs(date_str: str) -> int:
    with database.connect() as conn:
        n = conn.execute("DELETE FROM journal.activity_logs WHERE category='training' AND date=%s",
                         (date_str,)).rowcount
        conn.commit()
        return n


def delete_activity_log(log_id: int) -> bool:
    with database.connect() as conn:
        n = conn.execute("DELETE FROM journal.activity_logs WHERE id=%s", (log_id,)).rowcount
        conn.commit()
        return n > 0


# ---------- activities, oxygen ----------

def get_activities_df(days: int | None = None, limit: int | None = None) -> pd.DataFrame:
    where, params = "", []
    if days and days > 0:
        where, params = "WHERE date >= %s", [_iso_days_ago(days)]
    tail = f"LIMIT {int(limit)}" if limit and limit > 0 else ""
    rows = _rows(f"""SELECT activity_id, date::text AS date, started_local::text AS start_time,
                            name AS activity_name, type AS activity_type, duration_seconds,
                            elapsed_duration_seconds, distance_meters, calories, avg_hr, max_hr,
                            aerobic_training_effect, anaerobic_training_effect, avg_speed, max_speed,
                            elevation_gain, steps
                     FROM health.activities {where} ORDER BY started_local DESC NULLS LAST, activity_id DESC {tail}""",
                 params)
    return pd.DataFrame(rows)


def get_spo2_epochs_df(date_str: str) -> pd.DataFrame:
    rows = _rows("""SELECT date::text AS date, ts, value AS spo2_value, respiration_rate,
                           'Unknown' AS sleep_stage, source AS epoch_type
                    FROM health.spo2_samples WHERE date=%s ORDER BY ts""", (date_str,))
    for r in rows:
        ts = r.pop("ts")
        r["timestamp"] = int(ts.timestamp())
        r["time_str"] = _local(ts, "%H:%M:%S")
    return pd.DataFrame(rows, columns=["date", "timestamp", "time_str", "spo2_value", "respiration_rate",
                                       "sleep_stage", "epoch_type"])


def get_spo2_quality(date_str: str) -> dict:
    rows = _rows("SELECT availability, sample_count, reason FROM health.spo2_processing WHERE date=%s", (date_str,))
    return rows[0] if rows else {"availability": "unavailable", "sample_count": 0,
                                 "reason": "No oxygen detail has been verified for this date."}


# ---------- alerts, plans, reports ----------

def get_recent_alerts(limit: int | None = 20, unacknowledged_only: bool = False) -> list[dict]:
    where = "WHERE alert_state='active'" + (" AND NOT acknowledged" if unacknowledged_only else "")
    tail = "" if limit is None else f"LIMIT {int(limit)}"
    return _stamp(_rows(f"""SELECT id, date::text AS date, ts, severity, alert_type, message, metrics,
                                   acknowledged, delivered
                            FROM journal.anomaly_alerts {where} ORDER BY ts DESC, id DESC {tail}"""))


def upsert_alert(date_str: str, severity: str, alert_type: str, message: str, metrics: dict, version: str) -> None:
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO journal.anomaly_alerts (date, severity, alert_type, message, metrics, algorithm_version)
               VALUES (%s,%s,%s,%s,%s::jsonb,%s)
               ON CONFLICT (date, alert_type, algorithm_version) DO UPDATE SET
                 message=excluded.message, metrics=excluded.metrics, alert_state='active',
                 delivered = CASE WHEN journal.anomaly_alerts.message = excluded.message
                                   AND journal.anomaly_alerts.alert_state = 'active'
                                  THEN journal.anomaly_alerts.delivered ELSE FALSE END""",
            (date_str, severity, alert_type, message, json.dumps(metrics, default=str), version))
        conn.commit()


def resolve_alert(date_str: str, alert_type: str, version: str) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE journal.anomaly_alerts SET alert_state='resolved' "
                     "WHERE date=%s AND alert_type=%s AND algorithm_version=%s", (date_str, alert_type, version))
        conn.commit()


def pending_alert(date_str: str, alert_type: str, version: str) -> dict | None:
    rows = _rows("SELECT id, delivered FROM journal.anomaly_alerts WHERE date=%s AND alert_type=%s "
                 "AND algorithm_version=%s", (date_str, alert_type, version))
    return rows[0] if rows else None


def mark_alert_delivered(alert_id: int) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE journal.anomaly_alerts SET delivered=TRUE WHERE id=%s", (alert_id,))
        conn.commit()


def get_latest_action_plan() -> dict | None:
    rows = _rows("""SELECT id, period_start::text AS period_start, period_end::text AS period_end,
                           generated_at::text AS generated_at, model, headline, plan_text
                    FROM journal.action_plans ORDER BY period_end DESC, id DESC LIMIT 1""")
    return rows[0] if rows else None


def get_latest_coaching_report() -> dict | None:
    rows = _rows("""SELECT id, date::text AS date, generated_at::text AS generated_at, report_text,
                           evidence, model, validation
                    FROM journal.coaching_reports ORDER BY generated_at DESC, id DESC LIMIT 1""")
    return rows[0] if rows else None


def save_coaching_report(date_str: str, text: str, evidence: dict, model: str, validation: str) -> int:
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.coaching_reports (date, report_text, evidence, model, validation)
               VALUES (%s,%s,%s::jsonb,%s,%s) RETURNING id""",
            (date_str, text, json.dumps(evidence, default=str), model, validation)).fetchone()
        conn.commit()
        return row[0]


def save_action_plan(period_start: str, period_end: str, model: str, headline: str, plan_text: str,
                     watchlist: list, evidence: dict | None = None) -> int:
    with database.connect() as conn:
        row = conn.execute(
            """INSERT INTO journal.action_plans (period_start, period_end, model, headline, plan_text,
                                                 watchlist, evidence)
               VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING id""",
            (period_start, period_end, model, headline, plan_text, json.dumps(watchlist),
             json.dumps(evidence, default=str))).fetchone()
        conn.commit()
        return row[0]


def get_activity_logs_between(start: str, end: str) -> list[dict]:
    """Every entry dated start..end inclusive (ISO dates), newest first."""
    return _stamp(_rows(
        f"SELECT {_LOG_COLUMNS} FROM journal.activity_logs WHERE date >= %(a)s AND date <= %(b)s "
        "ORDER BY date DESC, ts DESC, id DESC", {"a": start, "b": end}))


# ---------- evening check-in ----------

CHECKIN_COLUMNS = {"alcohol_units": float, "late_caffeine": bool, "late_meal": bool, "rpe": int,
                   "wake_feeling": int}


def save_checkin_answer(date_str: str, field: str, value) -> None:
    """Record one answer. `field` is whitelisted; other fields on the day are left as they were."""
    if field not in CHECKIN_COLUMNS:
        raise ValueError(f"unknown check-in field {field!r}")
    cast = CHECKIN_COLUMNS[field]
    converted = bool(int(value)) if cast is bool else cast(value)
    with database.connect() as conn:
        conn.execute(
            f"INSERT INTO journal.checkins (date, {field}) VALUES (%s, %s) "
            f"ON CONFLICT (date) DO UPDATE SET {field} = EXCLUDED.{field}, answered_at = NOW()",
            (date_str, converted))
        conn.commit()


def get_checkin(date_str: str) -> dict | None:
    rows = _rows("SELECT date::text AS date, alcohol_units, late_caffeine, late_meal, rpe, wake_feeling "
                 "FROM journal.checkins WHERE date = %(d)s", {"d": date_str})
    if not rows:
        return None
    row = rows[0]
    if row.get("alcohol_units") is not None:
        row["alcohol_units"] = float(row["alcohol_units"])
    return row


def get_wake_feelings(start: str, end: str) -> dict[str, int]:
    """{date: 1..5} for the days in start..end that were rated. Unrated days are absent."""
    rows = _rows("SELECT date::text AS date, wake_feeling FROM journal.checkins "
                 "WHERE date >= %(a)s AND date <= %(b)s AND wake_feeling IS NOT NULL", {"a": start, "b": end})
    return {r["date"]: int(r["wake_feeling"]) for r in rows}
