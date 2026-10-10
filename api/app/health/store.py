"""Persistence for one Garmin day.

save_day() is one transaction: the endpoint merge, the immutable payload
archive, daily metrics, oxygen samples and activities all commit together or
not at all, serialised per date by an advisory lock.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from psycopg import Connection
from psycopg.types.json import Jsonb

from . import quality

FLOAT_COLUMNS = {"spo2_avg", "spo2_min", "respiration_avg", "respiration_min"}
TEXT_COLUMNS = {"hrv_status"}


def _coerce(column: str, value):
    if value is None:
        return None
    if column in TEXT_COLUMNS:
        return str(value)
    if column in FLOAT_COLUMNS:
        return float(value)
    return int(round(value))


def _ts(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_previous(conn: Connection, day: date) -> dict:
    previous: dict = {"_sources": {}}
    rows = conn.execute(
        """SELECT endpoint, status, payload, fetched_at, attempted_at, payload_hash, retained
           FROM health.endpoint_state WHERE date = %s""", (day,)).fetchall()
    for endpoint, status, payload, fetched_at, attempted_at, payload_hash, retained in rows:
        state = {"status": status, "retained": retained}
        if fetched_at:
            state["fetched_at"] = fetched_at.isoformat()
        if attempted_at:
            state["attempted_at"] = attempted_at.isoformat()
        if payload_hash:
            state["payload_hash"] = payload_hash
        previous["_sources"][endpoint] = state
        if payload is not None:
            previous[endpoint] = payload
    return previous


def save_day(conn: Connection, date_str: str, incoming: dict, *, fetched_at: str | None = None) -> dict:
    """Merge a fetched day into the store. Returns the merged source payloads.

    `fetched_at` is only for history imports: it records when the data was
    really received instead of stamping it with the import time."""
    day = date.fromisoformat(date_str)
    incoming = {**incoming, "date": date_str}
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("health:" + date_str,))
        previous = _load_previous(conn, day)
        merged = quality.merge_sources(previous, incoming, fetched_at)

        # Archive raw evidence first: nothing received is ever overwritten.
        for source in quality.SOURCES:
            if source in incoming:
                conn.execute(
                    """INSERT INTO health.source_payloads (date, endpoint, payload_hash, payload)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (day, source, quality.payload_hash(incoming[source]),
                     Jsonb(incoming[source], dumps=lambda o: json.dumps(o, default=str))))

        for source in sorted(quality.SOURCES):
            state = merged["_sources"][source]
            has_payload = source in merged
            conn.execute(
                """INSERT INTO health.endpoint_state
                     (date, endpoint, status, payload, fetched_at, attempted_at, payload_hash, retained)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (date, endpoint) DO UPDATE SET
                     status=excluded.status, payload=excluded.payload, fetched_at=excluded.fetched_at,
                     attempted_at=excluded.attempted_at, payload_hash=excluded.payload_hash,
                     retained=excluded.retained""",
                (day, source, state["status"],
                 Jsonb(merged[source], dumps=lambda o: json.dumps(o, default=str)) if has_payload else None,
                 _ts(state.get("fetched_at")), _ts(state.get("attempted_at")),
                 state.get("payload_hash"), bool(state.get("retained"))))

        _save_daily(conn, day, merged, synced_at=_ts(fetched_at))
        _save_oxygen(conn, day, merged)
        _save_activities(conn, day, merged)
    return merged


def _save_daily(conn: Connection, day: date, merged: dict, synced_at=None) -> None:
    values, provenance, issues = quality.parse_daily(merged)
    columns = list(values)
    params = [_coerce(c, values[c]) for c in columns]
    assignments = ", ".join(f"{c}=excluded.{c}" for c in columns)
    conn.execute(
        f"""INSERT INTO health.daily_metrics (date, {', '.join(columns)}, metric_sources, metric_issues, synced_at)
            VALUES (%s, {', '.join(['%s'] * len(columns))}, %s, %s, COALESCE(%s, NOW()))
            ON CONFLICT (date) DO UPDATE SET {assignments},
              metric_sources=excluded.metric_sources, metric_issues=excluded.metric_issues,
              synced_at=excluded.synced_at""",
        [day, *params, Jsonb(provenance), Jsonb(issues), synced_at])


def _save_oxygen(conn: Connection, day: date, merged: dict) -> None:
    epochs, state = quality.parse_oxygen(day.isoformat(), merged)
    conn.execute("DELETE FROM health.spo2_samples WHERE date = %s", (day,))
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO health.spo2_samples (date, ts, value, respiration_rate, source)
               VALUES (%s, to_timestamp(%s), %s, %s, %s)""",
            [(day, e["timestamp"], e["spo2_value"], e["respiration_rate"], e["epoch_type"]) for e in epochs])
    conn.execute(
        """INSERT INTO health.spo2_processing
             (date, algorithm_version, availability, sample_count, rejected_samples, reason)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (date) DO UPDATE SET algorithm_version=excluded.algorithm_version,
             availability=excluded.availability, sample_count=excluded.sample_count,
             rejected_samples=excluded.rejected_samples, reason=excluded.reason, processed_at=NOW()""",
        (day, state["algorithm_version"], state["availability"], state["sample_count"],
         state["rejected_samples"], state["reason"]))


def _activity_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        found = raw.get("activities") or raw.get("Activities") or raw.get("activityList")
        return found if isinstance(found, list) else [raw] if raw else []
    return []


def _save_activities(conn: Connection, day: date, merged: dict) -> None:
    labels = []
    num = quality.number
    for item in _activity_list(merged.get("activities")):
        if not isinstance(item, dict) or not item.get("activityId"):
            continue
        start = item.get("startTimeLocal") or item.get("startTimeGMT")
        started_local = None
        act_day = day
        if isinstance(start, str) and len(start) >= 10:
            try:
                act_day = date.fromisoformat(start[:10])
            except ValueError:
                act_day = day
            if len(start) >= 19:
                try:
                    started_local = datetime.fromisoformat(start[:19].replace(" ", "T"))
                except ValueError:
                    started_local = None
        type_obj = item.get("activityType")
        act_type = type_obj.get("typeKey") if isinstance(type_obj, dict) else str(type_obj or "unknown")
        name = item.get("activityName") or act_type.replace("_", " ").title()
        duration = num(quality.first_value(item, "duration", "elapsedDuration"))
        distance = num(item.get("distance"))
        steps = num(item.get("steps"))
        conn.execute(
            """INSERT INTO health.activities
                 (activity_id, date, started_local, name, type, duration_seconds, elapsed_duration_seconds,
                  distance_meters, calories, avg_hr, max_hr, aerobic_training_effect,
                  anaerobic_training_effect, avg_speed, max_speed, elevation_gain, steps, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (activity_id) DO UPDATE SET
                 date=excluded.date, started_local=excluded.started_local, name=excluded.name,
                 type=excluded.type, duration_seconds=excluded.duration_seconds,
                 elapsed_duration_seconds=excluded.elapsed_duration_seconds,
                 distance_meters=excluded.distance_meters, calories=excluded.calories,
                 avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,
                 aerobic_training_effect=excluded.aerobic_training_effect,
                 anaerobic_training_effect=excluded.anaerobic_training_effect,
                 avg_speed=excluded.avg_speed, max_speed=excluded.max_speed,
                 elevation_gain=excluded.elevation_gain, steps=excluded.steps, raw=excluded.raw""",
            (int(item["activityId"]), act_day, started_local, name, act_type, duration,
             num(quality.first_value(item, "elapsedDuration", "duration")), distance,
             num(quality.first_value(item, "calories", "activeKilocalories")),
             num(quality.first_value(item, "averageHR", "averageHeartRate")),
             num(quality.first_value(item, "maxHR", "maxHeartRate")),
             num(item.get("aerobicTrainingEffect")), num(item.get("anaerobicTrainingEffect")),
             num(item.get("averageSpeed")), num(item.get("maxSpeed")), num(item.get("elevationGain")),
             None if steps is None else int(steps),
             Jsonb(item, dumps=lambda o: json.dumps(o, default=str))))
        details = []
        if distance is not None and distance / 1000 > 0.1:
            details.append(f"{distance / 1000:.1f} km")
        if duration is not None:
            details.append(f"{int(round(duration / 60))}m")
        label = act_type.replace("_", " ").title()
        labels.append(f"{label} ({', '.join(details)})" if details else label)
    if labels:
        conn.execute("UPDATE health.daily_metrics SET workout_type=%s WHERE date=%s",
                     (", ".join(labels), day))
