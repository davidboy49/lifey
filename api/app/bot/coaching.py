"""Deterministic coaching evidence; the optional language model can select, not invent."""
import json
from datetime import timedelta
import pandas as pd
from app.health import quality

VERSION = "evidence-v1"
METRICS = {
    "hrv_last_night": ("HRV", "ms", "hrv"),
    "hrv_weekly_avg": ("Garmin weekly HRV", "ms", "hrv"),
    "resting_hr": ("Resting heart rate", "bpm", "summary"),
    "sleep_score": ("Sleep score", "/100", "sleep"),
    "sleep_duration": ("Sleep duration", "hours", "sleep"),
    "training_readiness": ("Garmin training readiness", "/100", "training_readiness"),
    "stress_avg": ("Daily average stress", "/100", "summary"),
    "steps": ("Steps", "steps", "summary"),
    "spo2_avg": ("Garmin daily average SpO2", "%", "summary"),
    "spo2_min": ("Garmin daily minimum SpO2", "%", "summary"),
}


def build_evidence(df, days=7):
    if df.empty:
        return {"version": VERSION, "facts": [], "actions": [], "period_start": None,
                "period_end": None, "notice": "No recorded data is available."}
    frame = df.copy().sort_values("date")
    end = pd.Timestamp(frame.iloc[-1]["date"])
    frame = frame[pd.to_datetime(frame["date"]) >= end - pd.Timedelta(days=days - 1)]
    facts = []
    for _, row in frame.iterrows():
        raw = row.get("raw_json")
        try:
            raw = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
        except (ValueError, TypeError):
            raw = {}
        states = raw.get("_sources", {})
        for metric, (label, unit, source) in METRICS.items():
            value = quality.number(row.get(metric))
            state = raw.get("_metric_sources", {}).get(metric, states.get(source, {}))
            if state.get("status") not in {"available", "not_recorded"} or value is None:
                continue
            if metric == "sleep_duration":
                value /= 3600
            fid = f"{row['date']}:{metric}"
            facts.append({"id": fid, "metric": metric, "date": str(row["date"]), "value": value,
                          "source_hash": state.get("payload_hash"), "source_fetched_at": state.get("fetched_at"),
                          "text": f"{row['date']}: {label} {value:.2f} {unit} (Garmin-reported)."})
    last_date = str(frame.iloc[-1]["date"])
    stale = pd.Timestamp(last_date).date() < quality.today() - timedelta(days=1)
    actions = []
    # Proposed conservative wellness rules, explicitly not a recovery forecast.
    if not stale:
        for fact in facts:
            if fact["date"] != last_date:
                continue
            if fact["metric"] == "sleep_duration" and fact["value"] < 7:
                actions.append({"id": "sleep_consistency", "evidence_ids": [fact["id"]],
                    "text": "Consider protecting your next sleep opportunity; the recorded duration was below 7 hours."})
            if fact["metric"] == "training_readiness" and fact["value"] < 50:
                actions.append({"id": "training_checkin", "evidence_ids": [fact["id"]],
                    "text": "Consider a lighter session and check how you feel before increasing intensity; Garmin readiness was below 50/100."})
    return {"version": VERSION, "facts": facts, "actions": actions,
            "period_start": str(frame.iloc[0]["date"]), "period_end": last_date,
            "notice": "Historical data: refresh your watch before using this for today's decisions." if stale else
                      "Only successfully sourced metrics are included. Missing or stale sources are omitted. Suggestions use simple wellness rules; no recovery date is predicted."}


def validate_selection(selection, evidence):
    if not isinstance(selection, dict) or set(selection) != {"fact_ids", "action_ids"}:
        return False
    for key, pool in (("fact_ids", "facts"), ("action_ids", "actions")):
        ids = selection[key]
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            return False
        allowed = {item["id"] for item in evidence[pool]}
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= allowed:
            if key == "action_ids" and ids == []:
                continue
            return False
    required = {fid for action in evidence["actions"] if action["id"] in selection["action_ids"]
                for fid in action["evidence_ids"]}
    return required <= set(selection["fact_ids"])


def render(evidence, selection=None):
    if not evidence["facts"]:
        return "No verified source metrics are available for coaching. Sync or rebuild source provenance first."
    if not validate_selection(selection, evidence):
        latest_fact_date = max(f["date"] for f in evidence["facts"])
        selection = {"fact_ids": [f["id"] for f in evidence["facts"] if f["date"] == latest_fact_date],
                     "action_ids": [a["id"] for a in evidence["actions"]]}
    lines = [f"Recorded period: {evidence['period_start']} to {evidence['period_end']}", evidence["notice"], "", "Recorded facts:"]
    lines.extend(f"- {f['text']} [{f['id']}]" for f in evidence["facts"] if f["id"] in selection["fact_ids"])
    if selection["action_ids"]:
        lines.extend(["", "Optional coaching suggestions:"])
        lines.extend(f"- {a['text']} [{', '.join(a['evidence_ids'])}]" for a in evidence["actions"] if a["id"] in selection["action_ids"])
    else:
        lines.extend(["", "No additional training instruction is justified by these rules and available data."])
    return "\n".join(lines)
