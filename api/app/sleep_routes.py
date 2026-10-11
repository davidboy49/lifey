"""GET /api/sleep: debt, target progress, regularity, outcomes and suggestions."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends

from . import db, sleep_advice as advice, sleep_report as sr
from .auth.deps import current_user
from .bot import store, training_plan
from .health import quality
from .journal import entries as e
from .journal import review as review_mod

router = APIRouter(prefix="/api/sleep", tags=["sleep"], dependencies=[Depends(current_user)])

HISTORY_DAYS = 60
SHOWN_NIGHTS = 42
HABITS_CONSIDERED = ("late_caffeine", "alcohol", "late_screen", "late_meal", "nicotine", "mental_stress")


def _public(n: dict) -> dict:
    return {"date": n["date"], "hours": None if n["hours"] is None else round(n["hours"], 2), "kind": sr.kind(n),
            "score": n["score"], "bed": n["bed"], "wake": n["wake"], "hrv": n["hrv"]}


@router.get("")
def sleep_overview() -> dict:
    today = quality.today()
    with db.connect() as conn:
        nights = sr.load_nights(conn, today, HISTORY_DAYS)
    start = (today - timedelta(days=HISTORY_DAYS - 1)).isoformat()
    logs = store.get_activity_logs_between(start, today.isoformat())

    # one mood value per day: the latest check-in that day
    mood_by_day: dict[str, float] = {}
    for log in sorted(logs, key=lambda l: (str(l["date"]), str(l.get("timestamp") or ""), l.get("id") or 0)):
        if log.get("category") == "wellbeing" and log.get("tag") == "mood" and log.get("value") is not None:
            mood_by_day[str(log["date"])[:10]] = float(log["value"])

    activities = store.get_activities_df(days=HISTORY_DAYS)
    trained = training_plan.trained_sessions(
        store.get_training_logs(days=HISTORY_DAYS), [] if activities.empty else activities.to_dict("records"))
    trained_days = {d.isoformat() for d in trained}

    progress = sr.target_progress(nights)
    debt = sr.debt(nights)
    reg = sr.regularity(nights)
    weekend = sr.weekend_split(nights)
    outcomes = sr.outcomes(nights, mood_by_day, trained_days)

    need = None
    for n in reversed(nights):
        if n["garmin_need_next_h"] is not None:
            need = {"hours": round(n["garmin_need_next_h"], 1), "baseline_h": round(n["garmin_need_base_h"] or 0, 1),
                    "feedback": n["garmin_need_feedback"], "as_of": n["date"]}
            break

    logged = {e.habit_tag(l) for l in logs if e.kind(l) == "habit"}
    tags = [t for t in HABITS_CONSIDERED if t in logged]
    labels = {t: e.habit_label(t) for t in tags}
    daily_rows = [{"date": n["date"], "sleep_score": n["score"]} for n in nights]
    patterns = review_mod.pattern_candidates(logs, daily_rows, tags, today, labels) if tags else []

    tips = sr.suggestions(progress, debt, reg, weekend, need, patterns)
    used = {eid for t in tips for eid in t["evidence"]}
    last = nights[-1]

    # Walker's published tips against the last 14 days of the person's own entries.
    window_start = (today - timedelta(days=advice.CHECK_DAYS - 1)).isoformat()
    recent = [l for l in logs if str(l["date"])[:10] >= window_start]
    entry_days = {str(l["date"])[:10] for l in recent}
    habit_days: dict[str, set[str]] = {}
    for l in recent:
        if e.kind(l) == "habit":
            habit_days.setdefault(e.habit_tag(l), set()).add(str(l["date"])[:10])
    training_days = len({d for d in trained_days if d >= window_start})
    awake = advice.awake_average(nights)
    walker = advice.walker_tips({t: len(v) for t, v in habit_days.items()}, len(entry_days), reg, awake, training_days)
    evidence = {**sr.EVIDENCE, **advice.EXTRA_EVIDENCE}

    return {
        "today": today.isoformat(),
        "target_h": sr.SLEEP_TARGET_H,
        "incomplete_below_h": sr.MIN_PLAUSIBLE_SLEEP_H,
        "last_night": _public(last),
        "nights": [_public(n) for n in nights[-SHOWN_NIGHTS:]],
        "progress": progress,
        "debt": debt,
        "regularity": reg,
        "weekend": weekend,
        "outcomes": outcomes,
        "garmin_need": need,
        "suggestions": tips,
        "walker": {
            "source": "walker2017",
            "critique": "guzey2019",
            "tips": walker,
            "window_days": advice.CHECK_DAYS,
        },
        "doctor": {
            "source": "aasm_talk",
            "topics": advice.doctor_topics(),
            "flags": advice.doctor_flags(debt, reg, awake),
            "summary": advice.doctor_summary(nights, reg, awake, today.isoformat()),
        },
        "evidence": evidence,
        "evidence_used": sorted(used),
    }
