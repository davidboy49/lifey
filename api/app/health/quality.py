"""Source provenance and measured-only oxygen parsing. No network or database I/O.

Ported unchanged in behaviour from vidhealth/data_quality.py; its regression
tests live in tests/test_quality.py."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
import os

OXYGEN_VERSION = "measured-v1"
SOURCES = {"summary", "hrv", "sleep", "heart_rate", "body_battery", "stress",
           "steps", "training_readiness", "pulse_ox", "respiration", "activities"}
ERROR_NAMES = {"hr_error": "heart_rate", "readiness_error": "training_readiness"}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def first_value(mapping, *keys):
    return next((mapping[k] for k in keys if mapping.get(k) is not None), None)


def user_timezone():
    return ZoneInfo(os.getenv("HEALTH_TIMEZONE", "Asia/Phnom_Penh"))


def today():
    return datetime.now(user_timezone()).date()


def timestamp_seconds(value):
    ts = number(value)
    if ts is None and isinstance(value, str):
        # Garmin sleep epochTimestamp is an ISO string in GMT. A comparison
        # with sleepStartTimestampGMT in the archived payload confirms UTC.
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            ts = parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
        except ValueError:
            return None
    if ts is None or ts <= 0:
        return None
    if ts >= 100_000_000_000:
        ts /= 1000
    # Reject implausible units instead of guessing from a duration.
    return int(ts) if 946684800 <= ts <= 4102444800 else None


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


SUMMARY_FIELDS = {
    "resting_hr": "restingHeartRate", "min_hr": "minHeartRate", "max_hr": "maxHeartRate",
    "stress_avg": "averageStressLevel", "stress_max": "maxStressLevel", "steps": "totalSteps",
    "spo2_avg": "averageSpo2", "spo2_min": "lowestSpo2", "respiration_avg": "avgWakingRespirationValue",
    "respiration_min": "lowestRespirationValue", "bb_max": "bodyBatteryHighestValue",
    "bb_min": "bodyBatteryLowestValue", "bb_charged": "bodyBatteryChargedValue",
    "bb_drained": "bodyBatteryDrainedValue", "training_readiness": "trainingReadiness", "floors": "floorsAscended",
}


def parse_daily(raw):
    """Map explicit Garmin fields, retaining per-metric source paths and validity."""
    values, provenance, issues = {}, {}, {}

    def read(metric, source, *path):
        node = raw.get(source)
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        val = node if metric == "hrv_status" and isinstance(node, str) else number(node)
        if metric != "hrv_status" and val is not None:
            bounded = metric in {"stress_avg", "stress_max", "sleep_score", "training_readiness", "bb_max", "bb_min", "spo2_avg", "spo2_min"}
            if val < 0 or (bounded and val > 100) or (metric in {"spo2_avg", "spo2_min"} and val == 0):
                issues[metric] = "Out-of-range source value"
                val = None
        values[metric] = val
        provenance[metric] = {"endpoint": source, "path": ".".join((source, *path)),
                              **raw.get("_sources", {}).get(source, {"status": "legacy_unverified"})}

    for metric, field in SUMMARY_FIELDS.items():
        read(metric, "summary", field)
    for metric, field in {"hrv_last_night": "lastNightAvg", "hrv_weekly_avg": "weeklyAvg", "hrv_status": "status"}.items():
        read(metric, "hrv", "hrvSummary", field)
    for metric, field in {"sleep_duration": "sleepTimeSeconds", "sleep_deep": "deepSleepSeconds",
                          "sleep_light": "lightSleepSeconds", "sleep_rem": "remSleepSeconds", "sleep_awake": "awakeSleepSeconds"}.items():
        read(metric, "sleep", "dailySleepDTO", field)
    read("sleep_score", "sleep", "dailySleepDTO", "sleepScores", "overall", "value")
    # Sleep belongs to the wake-up date. Garmin labels the record with that date as
    # calendarDate; if it disagrees with the day we asked for, never store it here.
    sleep_dto = raw.get("sleep", {}).get("dailySleepDTO") if isinstance(raw.get("sleep"), dict) else None
    sleep_day = sleep_dto.get("calendarDate") if isinstance(sleep_dto, dict) else None
    if sleep_day and raw.get("date") and str(sleep_day)[:10] != str(raw["date"])[:10]:
        for metric in ("sleep_duration", "sleep_deep", "sleep_light", "sleep_rem", "sleep_awake", "sleep_score"):
            values[metric] = None
            issues[metric] = f"Sleep record is for {str(sleep_day)[:10]}, not {str(raw['date'])[:10]}"
    for metric, field in {"resting_hr": "restingHeartRate", "min_hr": "minHeartRate", "max_hr": "maxHeartRate"}.items():
        if values[metric] is None:
            read(metric, "heart_rate", field)
    if values["training_readiness"] is None:
        read("training_readiness", "training_readiness", "score")
        if values["training_readiness"] is None:
            read("training_readiness", "training_readiness", "readinessQualifier", "readinessScore")
    if values["steps"] is None:
        steps = raw.get("steps")
        if isinstance(steps, dict):
            read("steps", "steps", "totalSteps")
        elif isinstance(steps, list) and steps:
            buckets = [number(item.get("steps")) if isinstance(item, dict) else None for item in steps]
            if all(v is not None and v >= 0 for v in buckets):
                values["steps"] = sum(buckets)
                provenance["steps"] = {"endpoint": "steps", "path": "steps[].steps (sum)",
                                       **raw.get("_sources", {}).get("steps", {"status": "legacy_unverified"})}
    return values, provenance, issues


def merge_sources(previous, incoming, fetched_at=None):
    """Replace successful endpoints, retain failures with explicit stale provenance.

    An explicitly returned empty dict/list is a successful correction. Missing
    endpoints and errors preserve earlier data; scalar/malformed endpoints fail.
    Legacy values have unknown fetch times, never an invented fresh timestamp.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    merged = {k: v for k, v in previous.items() if k in SOURCES}
    states = dict(previous.get("_sources", {}))
    errors = {ERROR_NAMES.get(k, k.removesuffix("_error")): str(v)
              for k, v in incoming.items() if k.endswith("_error")}
    for source in sorted(SOURCES):
        old = dict(states.get(source, {}))
        if source in errors:
            states[source] = {**old, "status": "fetch_failed", "attempted_at": fetched_at,
                              "retained": source in merged}
        elif source in incoming:
            value = incoming[source]
            expected = (dict, list) if source in {"steps", "body_battery", "activities"} else (dict,)
            if not isinstance(value, expected) or (
                source == "sleep" and value.get("dailySleepDTO") is not None
                and not isinstance(value["dailySleepDTO"], dict)
            ):
                states[source] = {**old, "status": "parse_failed", "attempted_at": fetched_at,
                                  "retained": source in merged}
                continue
            merged[source] = value
            states[source] = {"status": "available" if value else "not_recorded",
                              "fetched_at": fetched_at, "attempted_at": fetched_at,
                              "payload_hash": payload_hash(value), "retained": False}
        elif source in merged:
            states[source] = {**old, "status": "stale", "retained": True}
        else:
            states[source] = {"status": "unavailable", "retained": False}
    merged.update(date=incoming.get("date", previous.get("date")), _sources=states)
    return merged


def _records(container, names):
    for key in names:
        value = container.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def parse_oxygen(date_str, raw):
    """Accept only explicit timestamped sensor values. Never synthesize samples.

    Supports the dictionary epoch shapes used by the existing adapter. Unknown
    array shapes are reported, so new device fixtures can be added deliberately.
    The source date labels a Garmin day/sleep record, not each sample's UTC day.
    """
    sleep = raw.get("sleep") or {}
    sleep = sleep if isinstance(sleep, dict) else {}
    daily = sleep.get("dailySleepDTO") or {}
    daily = daily if isinstance(daily, dict) else {}
    pulse = raw.get("pulse_ox") or {}
    pulse = pulse if isinstance(pulse, dict) else {}
    sleep_values = (_records(daily, ["wellnessEpochSPO2DataDTOList"])
                    or _records(sleep, ["wellnessEpochSPO2DataDTOList"]))
    pulse_values = _records(pulse, ["spO2ContinuousValues", "timeOffsetEpochDTOList",
                                    "spO2SingleValues", "allSpO2Values"])
    resp_values = (_records(daily, ["wellnessEpochRespirationDataDTOList"])
                   or _records(sleep, ["wellnessEpochRespirationDataDTOList"]))
    respiration = {}
    for row in resp_values:
        if isinstance(row, dict):
            ts = timestamp_seconds(first_value(row, "epochTimestamp", "startTimeGMT"))
            val = number(first_value(row, "respirationValue", "value"))
            if ts is not None and val is not None and 0 < val < 100:
                respiration[ts] = val

    parsed = {}
    invalid = 0
    # Sleep wins only on the same timestamp; retain genuine daytime readings.
    for source, values in (("PULSE_OX", pulse_values), ("SLEEP", sleep_values)):
        for row in values:
            if not isinstance(row, dict):
                invalid += 1
                continue
            ts = timestamp_seconds(row.get("epochTimestamp"))
            val = number(first_value(row, "spo2Reading", "spO2Reading", "spo2", "value"))
            if ts is None or val is None or not 1 <= val <= 100:
                invalid += 1
                continue
            dt = datetime.fromtimestamp(ts, timezone.utc).astimezone(user_timezone())
            parsed[ts] = {"date": date_str, "timestamp": ts,
                          "time_str": dt.strftime("%H:%M:%S"), "spo2_value": val,
                          "respiration_rate": respiration.get(ts),
                          "sleep_stage": "Unknown", "epoch_type": source}
    epochs = sorted(parsed.values(), key=lambda row: row["timestamp"])
    status = "partial" if invalid and epochs else "available" if epochs else "parse_failed" if invalid else "unavailable"
    return epochs, {"availability": status, "sample_count": len(epochs),
                    "rejected_samples": invalid, "algorithm_version": OXYGEN_VERSION,
                    "reason": "Timestamped source samples only; cadence and coverage may vary."
                    if epochs else "No supported timestamped oxygen samples in the source payload."}


def measured_records(data):
    records = data.to_dict("records") if hasattr(data, "to_dict") else list(data or [])
    by_time = {}
    for row in records:
        if row.get("epoch_type") not in {"PULSE_OX", "SLEEP"}:
            continue
        ts = timestamp_seconds(row.get("timestamp"))
        val = number(row.get("spo2_value"))
        if ts is not None and val is not None and 1 <= val <= 100:
            by_time[ts] = {**row, "timestamp": ts, "spo2_value": val}
    return sorted(by_time.values(), key=lambda row: row["timestamp"])


def observed_intervals(data, max_gap_seconds=120):
    """Left-held sample intervals, excluding gaps and the unbounded last sample.

    This is an explicit exploratory integration policy, not a claim that the
    sensor observed continuously between samples. Never spans source types.
    """
    rows = measured_records(data)
    return [(a, b["timestamp"] - a["timestamp"])
            for a, b in zip(rows, rows[1:])
            if a["epoch_type"] == b["epoch_type"]
            and 0 < b["timestamp"] - a["timestamp"] <= max_gap_seconds]
