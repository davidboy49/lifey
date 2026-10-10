"""
Quit tracker for Master: streaks, resisted urges, nightly check-ins, mood/energy,
and a comparison of the user's own next-day data after a Master day vs. other days.

Everything here is computed from what was actually logged. The comparison reports
differences in the user's own measurements; it never assumes an effect exists.
"""
from datetime import date, timedelta
import html

from app.health import quality

CATEGORY = "master"
RELAPSE_TAG = "master"          # also matches older rows saved as unholy_habit/master
URGE_TAG = "urge_resisted"
CLEAN_TAG = "clean_day"
WELLBEING_CATEGORY = "wellbeing"
REASON_CATEGORY = "quit_reason"

MIN_DAYS_PER_GROUP = 5

# (daily_metrics column or wellbeing tag, label, unit, higher_is_better)
COMPARED = [
    ("sleep_score", "Sleep score", "", True),
    ("hrv_last_night", "HRV", " ms", True),
    ("resting_hr", "Resting HR", " bpm", False),
    ("bb_max", "Body Battery peak", "", True),
    ("stress_avg", "Avg stress", "", False),
    ("mood", "Mood (1–5)", "", True),
    ("energy", "Energy (1–5)", "", True),
]


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def relapse_logs(logs):
    return [l for l in logs if l.get("tag") == RELAPSE_TAG]


def summarize(logs: list[dict], today: date) -> dict:
    """Streak and counts from activity-log rows (dicts with date, timestamp, category, tag, value)."""
    tracked = [l for l in logs if l.get("category") == CATEGORY or l.get("tag") == RELAPSE_TAG]
    relapses = relapse_logs(tracked)
    relapse_dates = sorted({_day(l["date"]) for l in relapses})
    start = min((_day(l["date"]) for l in tracked), default=None)
    last = relapse_dates[-1] if relapse_dates else None

    current = (today - (last or start)).days if (last or start) else 0
    gaps = [(b - a).days for a, b in zip(relapse_dates, relapse_dates[1:])]
    if relapse_dates and start and relapse_dates[0] > start:
        gaps.append((relapse_dates[0] - start).days)
    best = max(gaps + [current])

    last_relapse_ts = max((str(l.get("timestamp") or "") for l in relapses), default="")
    urges = [l for l in tracked if l.get("tag") == URGE_TAG]

    def count_since(days):
        cutoff = today - timedelta(days=days - 1)
        return sum(quality.number(l.get("value")) or 1 for l in relapses if _day(l["date"]) >= cutoff)

    return {
        "tracking_start": start,
        "last_relapse": last,
        "relapsed_today": last == today,
        "clean_checked_today": any(l.get("tag") == CLEAN_TAG and _day(l["date"]) == today for l in tracked),
        "current_streak": current,
        "best_streak": best,
        "urges_total": len(urges),
        "urges_this_streak": sum(1 for l in urges if str(l.get("timestamp") or "") > last_relapse_ts),
        "relapses_7d": count_since(7),
        "relapses_30d": count_since(30),
    }


def compare_next_day(logs: list[dict], daily_rows: list[dict]) -> dict:
    """
    Groups each tracked day D by whether Master was logged on D-1 (Garmin files the
    night's sleep/HRV under the morning's date), then averages each measure per group.
    Only days from the start of tracking are used, so untracked history can't pose as clean.
    """
    summary_start = min(
        (_day(l["date"]) for l in logs if l.get("category") == CATEGORY or l.get("tag") == RELAPSE_TAG),
        default=None,
    )
    if summary_start is None:
        return {"after": 0, "other": 0, "metrics": []}
    relapse_dates = {_day(l["date"]) for l in relapse_logs(logs)}

    values = {}
    for row in daily_rows:
        values.setdefault(_day(row["date"]), {}).update(
            {col: row.get(col) for col, *_ in COMPARED if col in row}
        )
    for l in logs:
        if l.get("category") == WELLBEING_CATEGORY and l.get("tag") in ("mood", "energy"):
            values.setdefault(_day(l["date"]), {})[l["tag"]] = l.get("value")

    groups = {"after": [], "other": []}
    for day, measures in values.items():
        if day - timedelta(days=1) < summary_start:
            continue
        groups["after" if day - timedelta(days=1) in relapse_dates else "other"].append(measures)

    metrics = []
    for col, label, unit, higher_better in COMPARED:
        after = [v for v in (quality.number(m.get(col)) for m in groups["after"]) if v is not None]
        other = [v for v in (quality.number(m.get(col)) for m in groups["other"]) if v is not None]
        metrics.append({
            "label": label, "unit": unit, "higher_is_better": higher_better,
            "after_n": len(after), "other_n": len(other),
            "after_avg": sum(after) / len(after) if after else None,
            "other_avg": sum(other) / len(other) if other else None,
            "enough": len(after) >= MIN_DAYS_PER_GROUP and len(other) >= MIN_DAYS_PER_GROUP,
        })
    return {"after": len(groups["after"]), "other": len(groups["other"]), "metrics": metrics}


def worse_after(c: dict) -> list[str]:
    """Measures that were reliably worse the day after Master, in the user's own data."""
    out = []
    for m in c["metrics"]:
        if not m["enough"]:
            continue
        diff = m["after_avg"] - m["other_avg"]
        if diff != 0 and (diff < 0) == m["higher_is_better"]:
            out.append(f"{m['label']}: {_fmt(m['after_avg'])}{m['unit']} vs {_fmt(m['other_avg'])}{m['unit']} usually")
    return out


def render_streak(s: dict) -> str:
    if s["tracking_start"] is None:
        return ("🔥 <b>Quit Tracker</b>\n\nNothing tracked yet. Tap 🧘 Urge when you resist one, "
                "💥 Master if you slip, and answer the nightly check-in. Your streak starts now.")
    lines = [
        "🔥 <b>Quit Tracker</b>\n",
        f"<b>Current streak:</b> {s['current_streak']} day{'s' if s['current_streak'] != 1 else ''}",
        f"<b>Best streak:</b> {s['best_streak']} days",
        f"<b>Urges resisted:</b> {s['urges_this_streak']} this streak · {s['urges_total']} total",
        f"<b>Slips:</b> {s['relapses_7d']:g} in last 7 days · {s['relapses_30d']:g} in last 30 days",
        f"<i>Tracking since {s['tracking_start']}</i>",
    ]
    return "\n".join(lines)


def _fmt(v):
    return "—" if v is None else f"{v:.1f}".rstrip("0").rstrip(".")


def render_comparison(c: dict) -> str:
    lines = [
        "📊 <b>Your data: the day after Master vs. other days</b>",
        f"<i>{c['after']} day(s) after Master · {c['other']} other day(s) since tracking began</i>\n",
    ]
    shown = False
    for m in c["metrics"]:
        if not (m["after_n"] or m["other_n"]):
            continue
        shown = True
        line = (f"• <b>{html.escape(m['label'])}:</b> after {_fmt(m['after_avg'])}{m['unit']} (n={m['after_n']}) "
                f"vs other {_fmt(m['other_avg'])}{m['unit']} (n={m['other_n']})")
        if m["enough"]:
            diff = m["after_avg"] - m["other_avg"]
            worse = (diff < 0) == m["higher_is_better"] and diff != 0
            line += f" → {'🔻 worse' if worse else ('same' if diff == 0 else '🔺 better')} after"
        else:
            line += " → need ≥5 days in each group"
        lines.append(line)
    if not shown:
        lines.append("No measurements yet for tracked days. Keep syncing Garmin and answering check-ins.")
    lines.append("\n<i>These are your own averages. A difference shows a pattern, not proof: "
                 "other things (late nights, stress, alcohol) can differ on those days too.</i>")
    return "\n".join(lines)
