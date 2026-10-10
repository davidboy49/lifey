"""The weekly review: assemble a week from the data Lifey already keeps.

Everything shown carries the number of days or nights behind it, and a pattern
is only called one once there is enough data. Lifey lays out the evidence; the
reflection is the person's own words.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

from . import entries as e
from . import habits as h

MIN_NIGHTS = 8          # nights needed in each group before a comparison counts as a pattern
USUAL_DAYS = 28         # days before the week used as "your usual"
USUAL_MIN = 10


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _by_date(rows: list[dict]) -> dict[date, dict]:
    return {date.fromisoformat(str(r["date"])[:10]): r for r in rows}


def _avg(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _numbers(week: list[date], prev: list[date], daily: dict[date, dict], logs: list[dict],
             quit_summary: dict, strip: list[dict], trained_days: set[date], today: date) -> dict:
    def col(days, name):
        return [v for d in days if d in daily and (v := _num(daily[d].get(name))) is not None]

    sleep = col(week, "sleep_duration")
    sleep_prev = col(prev, "sleep_duration")
    hrv = col(week, "hrv_last_night")
    before = [week[0] - timedelta(days=i) for i in range(1, USUAL_DAYS + 1)]
    usual_vals = col(before, "hrv_last_night")
    usual = _avg(usual_vals) if len(usual_vals) >= USUAL_MIN else None

    mood = []
    for log in logs:
        if log.get("category") == "wellbeing" and log.get("tag") == "mood" and (v := _num(log.get("value"))) is not None:
            mood.append(v)

    elapsed = [d for d in week if d <= today]
    slips = {c["date"] for c in strip if c["state"] == "slip"}
    tracking = quit_summary.get("tracking_start")
    tracked_days = [d for d in elapsed if tracking is not None and d >= tracking]
    logged_days = {e._day(l["date"]) for l in logs}

    return {
        "sleep": {"avg_seconds": _avg(sleep), "prev_avg_seconds": _avg(sleep_prev), "nights": len(sleep),
                  "of": len(elapsed)},
        "hrv": {"avg": _avg(hrv), "usual": usual, "mornings": len(hrv), "of": len(elapsed),
                "delta_pct": (100 * (_avg(hrv) - usual) / usual) if hrv and usual else None},
        "training": {"sessions": len(trained_days & set(week)), "target": 4},
        "quit": None if tracking is None else {
            "free_days": sum(1 for d in tracked_days if d.isoformat() not in slips),
            "tracked_days": len(tracked_days),
            "slips": sum(1 for d in tracked_days if d.isoformat() in slips),
            "days_with_entries": sum(1 for d in tracked_days if d in logged_days),
        },
        "mood": {"avg": _avg(mood), "count": len(mood)},
    }


def pattern_candidates(logs: list[dict], daily_rows: list[dict], tags_this_week: list[str],
                       today: date, labels: dict[str, str]) -> list[dict]:
    """Habit versus the sleep score of the following night.

    Garmin files a night's sleep under the morning's date, so a habit on day D
    is compared with the score on D+1. Days with no entries are unknown and
    are left out of the comparison group instead of counting as "no habit"."""
    daily = _by_date(daily_rows)
    known = {e._day(l["date"]) for l in logs}
    amounts: dict[str, set[date]] = {}
    for log in logs:
        if e.kind(log) == "habit" and (_num(log.get("value")) or 1) > 0:
            amounts.setdefault(e.habit_tag(log), set()).add(e._day(log["date"]))

    out = []
    for tag in tags_this_week:
        logged = amounts.get(tag, set())
        with_habit, without = [], []
        for d in known:
            if d >= today:
                continue                      # needs the following morning's data
            score = _num(daily.get(d + timedelta(days=1), {}).get("sleep_score"))
            if score is None:
                continue
            (with_habit if d in logged else without).append(score)
        if not with_habit:
            continue
        enough = len(with_habit) >= MIN_NIGHTS and len(without) >= MIN_NIGHTS
        a, b = fmean(with_habit), (fmean(without) if without else None)
        label = labels.get(tag, e.habit_label(tag))
        if enough:
            text = (f"On the {len(with_habit)} nights after {label.lower()}, sleep score averaged {a:.0f}, against "
                    f"{b:.0f} on the {len(without)} other nights. That is an association in your own data, "
                    "not proof that it caused the difference.")
        else:
            other = f"{b:.0f} on {len(without)} other nights" if b is not None else "no comparison nights yet"
            text = (f"After {label.lower()} on {len(with_habit)} night{'' if len(with_habit) == 1 else 's'}, sleep score "
                    f"averaged {a:.0f} ({other}). Lifey needs at least {MIN_NIGHTS} nights in each group before it "
                    "treats this as a pattern, so take it as a note.")
        out.append({"tag": tag, "label": label, "metric": "Sleep score", "with_n": len(with_habit),
                    "without_n": len(without), "with_avg": a, "without_avg": b,
                    "needed": MIN_NIGHTS, "enough": enough, "text": text})
    return out


def notes_of_the_week(logs: list[dict], limit: int = 8) -> list[dict]:
    out = []
    for log in logs:
        text = e._text(log.get("note"))
        if not text or text.lower() in e.BOT_DEFAULT_NOTES:
            continue
        k = e.kind(log)
        if k in ("training",):
            continue
        time_text, _ = e.entry_time(log)
        out.append({"date": str(log["date"])[:10], "time": time_text, "kind": k,
                    "title": {"note": "Note", "quit": e.QUIT_TITLES.get(log.get("tag"), "Quit"),
                              "habit": e.habit_label(e.habit_tag(log)), "checkin": "Check-in",
                              "reason": "Reason"}.get(k, "Note"),
                    "text": text})
    out.sort(key=lambda n: (n["date"], n["time"]))
    return out[:limit]
