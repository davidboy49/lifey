"""What the Claude connector can read: plain functions returning compact JSON.

Read-only, built on the same datasets as the Data page. A gap is null and is
counted, never turned into a zero, so Claude can say "no data" instead of
guessing. Free-text notes are the person's own words and are returned as data.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import mean

from .. import data_routes
from ..health import quality
from ..journal import entries as e

MAX_DAYS = 365
DEFAULT_DAYS = 14
MAX_ROWS = 400

# Daily metrics worth summarising, in the order they are shown.
METRICS = [
    ("sleep_hours", "Sleep (h)"), ("sleep_score", "Sleep score"), ("hrv_last_night", "HRV (ms)"),
    ("resting_hr", "Resting HR"), ("training_readiness", "Training readiness"), ("bb_max", "Body battery max"),
    ("stress_avg", "Stress avg"), ("steps", "Steps"), ("spo2_avg", "SpO2 avg"), ("respiration_avg", "Respiration"),
]


def clamp_days(days: int | None, default: int = DEFAULT_DAYS) -> int:
    try:
        n = int(days if days is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(1, min(MAX_DAYS, n))


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _summary(values: list[tuple[str, float | None]], prior: list[float]) -> dict:
    present = [(d, v) for d, v in values if v is not None]
    if not present:
        return {"days_with_data": 0}
    nums = [v for _, v in present]
    out = {"days_with_data": len(present), "days_missing": len(values) - len(present),
           "mean": round(mean(nums), 2), "min": round(min(nums), 2), "max": round(max(nums), 2),
           "latest": {"date": present[-1][0], "value": round(present[-1][1], 2)}}
    if prior:
        out["previous_period_mean"] = round(mean(prior), 2)
        out["change_vs_previous_period"] = round(mean(nums) - mean(prior), 2)
    return out


def health(days: int = DEFAULT_DAYS) -> dict:
    """Daily metrics: per-metric summary against the previous equal period, plus the daily rows."""
    n = clamp_days(days)
    both = data_routes.rows("daily_metrics", n * 2)
    cutoff = (quality.today() - timedelta(days=n - 1)).isoformat()
    now = [r for r in both if r["date"] >= cutoff]
    before = [r for r in both if r["date"] < cutoff]
    summary = {}
    for key, label in METRICS:
        series = [(r["date"], _num(r.get(key))) for r in now]
        prior = [v for v in (_num(r.get(key)) for r in before) if v is not None]
        summary[label] = _summary(series, prior)
    return {
        "window": {"days": n, "from": cutoff, "to": quality.today().isoformat()},
        "days_with_any_data": len(now),
        "summary": summary,
        "daily": [{k: v for k, v in r.items() if v is not None and k not in ("synced_at",)} for r in now[-MAX_ROWS:]],
        "note": "Missing values are absent (not zero). 'partial' in source means a Garmin endpoint failed that day.",
    }


def activities(days: int = 30) -> dict:
    n = clamp_days(days, 30)
    found = data_routes.rows("activities", n)
    return {"window_days": n, "count": len(found),
            "activities": [{k: v for k, v in r.items() if v is not None} for r in found[-MAX_ROWS:]]}


def journal(days: int = DEFAULT_DAYS, kind: str | None = None) -> dict:
    """Journal entries, newest first. `kind`: note, habit, checkin, quit, training."""
    n = clamp_days(days)
    from .. import attachments
    found = data_routes.rows("journal", n)
    files = attachments.for_logs([r.get("id") for r in found])
    out, counts = [], Counter()
    for r in reversed(found):
        k = e.kind(r)
        counts[k] += 1
        if kind and k != kind:
            continue
        tag = e.habit_tag(r) if k == "habit" else r.get("tag")
        item = {"date": r["date"], "kind": k, "tag": tag, "note": r.get("note") or None, "value": r.get("value"),
                "recalled_later": bool(r.get("recalled")),
                "attachments": [a["filename"] for a in files.get(r.get("id"), [])] or None}
        out.append({kk: v for kk, v in item.items() if v not in (None, "", False)} | {"date": r["date"], "kind": k})
    return {"window_days": n, "entries_in_window": len(found), "by_kind": dict(counts),
            "entries": out[:MAX_ROWS],
            "note": "A day with no entries is unknown, not a clean day. recalled_later = written on a later day."}


def habits(days: int = 30) -> dict:
    n = clamp_days(days, 30)
    found = data_routes.rows("habits", n)
    per: dict[str, dict] = defaultdict(lambda: {"entries": 0, "total_units": 0.0, "days": set(), "notes": []})
    for r in found:
        tag = e.habit_tag({"tag": r.get("habit")})
        b = per[tag]
        b["entries"] += 1
        b["total_units"] += _num(r.get("units")) or 0
        b["days"].add(r["date"])
        if r.get("note") and len(b["notes"]) < 8:
            b["notes"].append(f"{r['date']}: {r['note']}")
    habits_out = []
    for tag, b in sorted(per.items(), key=lambda kv: -kv[1]["entries"]):
        habits_out.append({"habit": e.habit_label(tag), "tag": tag, "unit": e.habit_unit(tag),
                           "entries": b["entries"], "total_units": round(b["total_units"], 2),
                           "days_logged": len(b["days"]), "last_logged": max(b["days"]), "notes": b["notes"]})
    return {"window_days": n, "habits": habits_out,
            "note": "Counts are what was logged. Not logging a habit on a day does not prove it did not happen."}


def checkins(days: int = 30) -> dict:
    """Evening check-in answers. A day that was not answered is unknown, not a dry or easy day."""
    n = clamp_days(days, 30)
    found = data_routes.rows("checkins", n)
    answered = {f: [r for r in found if r.get(f) is not None] for f in ("alcohol_units", "late_caffeine", "late_meal", "rpe")}
    return {
        "window_days": n, "days_answered": len(found),
        "alcohol": {"days_asked": len(answered["alcohol_units"]),
                    "days_with_alcohol": sum(1 for r in answered["alcohol_units"] if r["alcohol_units"] > 0),
                    "total_drinks": round(sum(r["alcohol_units"] for r in answered["alcohol_units"]), 1)},
        "waking_feeling": {
            "days_rated": len([r for r in found if r.get("wake_feeling") is not None]),
            "mean": (round(mean(r["wake_feeling"] for r in found if r.get("wake_feeling") is not None), 2)
                     if any(r.get("wake_feeling") is not None for r in found) else None),
            "scale": "1 awful to 5 great, rated on waking before looking at the watch",
        },
        "late_caffeine_days": sum(1 for r in answered["late_caffeine"] if r["late_caffeine"]),
        "late_meal_days": sum(1 for r in answered["late_meal"] if r["late_meal"]),
        "workouts": {"days_asked": len(answered["rpe"]),
                     "days_trained": sum(1 for r in answered["rpe"] if r["rpe"] and r["rpe"] > 0)},
        "days": found[-MAX_ROWS:],
    }


def sleep() -> dict:
    """The Sleep page: debt, target progress, regularity, weekend split, and what the data suggests."""
    from ..sleep_routes import sleep_overview
    full = sleep_overview()
    keep = ("today", "target_h", "last_night", "progress", "debt", "regularity", "weekend", "outcomes",
            "garmin_need", "suggestions")
    out = {k: full[k] for k in keep if k in full}
    out["recent_nights"] = full["nights"][-14:]
    out["doctor_flags"] = full["doctor"]["flags"]
    return out


def digest(days: int = DEFAULT_DAYS) -> dict:
    """Everything needed for a written summary of the last N days, in one compact object."""
    n = clamp_days(days)
    h = health(n)
    j = journal(n)
    hb = habits(n)
    s = sleep()
    return {
        "window": h["window"],
        "health": {"days_with_any_data": h["days_with_any_data"], "summary": h["summary"]},
        "sleep": {k: s[k] for k in ("last_night", "progress", "debt", "regularity", "weekend", "suggestions")
                  if k in s} | {"doctor_flags": s["doctor_flags"]},
        "habits": hb["habits"],
        "checkins": checkins(n),
        "journal": {"by_kind": j["by_kind"],
                    "notes": [x for x in j["entries"] if x["kind"] in ("note", "checkin", "quit")][:60]},
        "reading_guide": ["Missing data is absent, never zero.",
                          "Observations are correlational, from one person's data; do not state causes.",
                          "Do not diagnose; suggest seeing a clinician for anything health-related that worries you."],
    }
