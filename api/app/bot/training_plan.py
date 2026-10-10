"""
Day-by-day gym plan: a 4-day upper/lower split for an intermediate lifter building
muscle and strength. Today's call (train / rest, which session, how hard) follows
simple scheduling rules plus the day's Garmin readiness, sleep and HRV. Every
adjustment names the measurement it came from; missing data is said to be missing.
"""
from datetime import date, timedelta

from app.health import quality

SESSIONS_PER_WEEK = 4
TRAINING_CATEGORY = "training"

SESSIONS = [
    {"key": "upper_a", "name": "Upper A · Heavy — chest, back, shoulders", "exercises": [
        ("Barbell bench press", "4 × 5–6"),
        ("Barbell row", "4 × 6–8"),
        ("Overhead press", "3 × 6–8"),
        ("Pull-ups or lat pulldown", "3 × 8–10"),
        ("Dumbbell curl", "2 × 10–12"),
        ("Triceps pushdown", "2 × 10–12"),
    ]},
    {"key": "lower_a", "name": "Lower A · Heavy — quads, hamstrings, glutes", "exercises": [
        ("Back squat", "4 × 5–6"),
        ("Romanian deadlift", "3 × 6–8"),
        ("Leg press", "3 × 10"),
        ("Lying leg curl", "3 × 10–12"),
        ("Standing calf raise", "3 × 10–12"),
        ("Plank", "3 × 45 s"),
    ]},
    {"key": "upper_b", "name": "Upper B · Volume — chest, back, shoulders, arms", "exercises": [
        ("Incline dumbbell press", "3 × 8–12"),
        ("Seated cable row", "3 × 10–12"),
        ("Dumbbell shoulder press", "3 × 10–12"),
        ("Lat pulldown (neutral grip)", "3 × 10–12"),
        ("Lateral raise", "3 × 12–15"),
        ("Incline dumbbell curl", "3 × 12"),
        ("Overhead triceps extension", "3 × 12"),
    ]},
    {"key": "lower_b", "name": "Lower B · Volume — legs, glutes, core", "exercises": [
        ("Deadlift", "3 × 4–5"),
        ("Bulgarian split squat", "3 × 8–10 each leg"),
        ("Leg extension", "3 × 12–15"),
        ("Seated leg curl", "3 × 12"),
        ("Hip thrust", "3 × 10"),
        ("Hanging leg raise", "3 × 10–15"),
    ]},
]

SESSION_KEYS = [x["key"] for x in SESSIONS]
SESSION_BY_KEY = {x["key"]: x for x in SESSIONS}
STYLE_NOTE = "<i>Heavy = more weight, fewer reps (strength). Volume = lighter, more reps (muscle size).</i>"

REST_DAY = [
    "20–40 min easy walk or bike (you can hold a conversation)",
    "10 min mobility: hips, thoracic spine, shoulders",
    "Aim for 7–9 h of sleep tonight — muscle is built while you recover",
]


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def trained_sessions(training_logs, activities) -> dict[date, str | None]:
    """Day -> session key logged that day (last one wins), or None for a Garmin
    strength activity with no session logged in the bot."""
    days = {_day(a["date"]): None for a in activities if "strength" in str(a.get("activity_type") or "").lower()}
    for l in training_logs:
        key = l.get("tag")
        days[_day(l["date"])] = key if key in SESSION_BY_KEY else days.get(_day(l["date"]))
    return days


def next_session(trained, day: date) -> dict:
    """The session after the last one done: a logged session sets the position,
    an unlabelled training day just moves one step on."""
    idx = 0
    for d in sorted(d for d in trained if d < day):
        key = trained[d] if isinstance(trained, dict) else None
        idx = SESSION_KEYS.index(key) + 1 if key in SESSION_BY_KEY else idx + 1
    return SESSIONS[idx % len(SESSIONS)]


def readiness(row: dict | None, today: date) -> dict:
    """Intensity from today's Garmin record. Returns level: normal / lighter / recover / unknown."""
    if not row or _day(row["date"]) != today:
        return {"level": "unknown", "reasons": ["No Garmin data for today yet — sync, or go by how you feel."]}
    tr = quality.number(row.get("training_readiness"))
    sleep = quality.number(row.get("sleep_duration"))
    hrv = quality.number(row.get("hrv_last_night"))
    hrv_week = quality.number(row.get("hrv_weekly_avg"))
    recover, lighter, seen = [], [], []
    if tr is not None:
        seen.append(f"readiness {tr:.0f}/100")
        if tr < 30:
            recover.append(f"Garmin training readiness is {tr:.0f}/100 (below 30)")
        elif tr < 50:
            lighter.append(f"Garmin training readiness is {tr:.0f}/100 (below 50)")
    if sleep is not None:
        hours = sleep / 3600
        seen.append(f"sleep {hours:.1f} h")
        if hours < 6:
            lighter.append(f"you slept {hours:.1f} h (under 6 h)")
    if hrv is not None and hrv_week:
        seen.append(f"HRV {hrv:.0f} ms vs {hrv_week:.0f} ms weekly avg")
        if hrv < 0.9 * hrv_week:
            lighter.append(f"HRV {hrv:.0f} ms is over 10% below your {hrv_week:.0f} ms weekly average")
    if not seen:
        return {"level": "unknown", "reasons": ["Today's Garmin record has no readiness, sleep or HRV yet."]}
    if recover:
        return {"level": "recover", "reasons": recover + lighter}
    if lighter:
        return {"level": "lighter", "reasons": lighter}
    return {"level": "normal", "reasons": [f"Looks good: {', '.join(seen)}."]}


def plan_day(trained: set[date], day: date, target: int = SESSIONS_PER_WEEK) -> dict:
    """Schedule-only decision for one day (readiness is applied separately for today)."""
    session = next_session(trained, day)
    if isinstance(trained, dict) and trained.get(day) in SESSION_BY_KEY:
        session = SESSION_BY_KEY[trained[day]]
    week_start = day - timedelta(days=day.weekday())
    done = sum(1 for d in trained if week_start <= d < day)
    if day in trained:
        return {"action": "done", "session": session, "done_this_week": done + 1,
                "why": "Already trained today."}
    remaining = target - done
    days_left = 7 - day.weekday()
    if remaining <= 0:
        return {"action": "rest", "session": session, "done_this_week": done,
                "why": f"All {target} sessions done this week."}
    if remaining >= days_left:
        return {"action": "train", "session": session, "done_this_week": done,
                "why": f"{remaining} session(s) left and {days_left} day(s) left this week."}
    if day - timedelta(days=1) in trained and day - timedelta(days=2) in trained:
        return {"action": "rest", "session": session, "done_this_week": done,
                "why": "You trained the last two days — recovery is when muscle grows."}
    return {"action": "train", "session": session, "done_this_week": done,
            "why": f"{done} of {target} sessions done this week."}


def plan_today(trained: set[date], today: date, row: dict | None) -> dict:
    plan = plan_day(trained, today)
    plan["readiness"] = readiness(row, today)
    if plan["action"] == "train" and plan["readiness"]["level"] == "recover":
        plan["action"] = "recover"
    return plan


def plan_week(trained: set[date], today: date, today_plan: dict) -> list[tuple[date, dict]]:
    """Today's plan plus a projection for the rest of the week, assuming planned sessions happen."""
    assumed = dict(trained) if isinstance(trained, dict) else dict.fromkeys(trained)
    days = []
    for offset in range(7 - today.weekday()):
        day = today + timedelta(days=offset)
        plan = today_plan if offset == 0 else plan_day(assumed, day)
        days.append((day, plan))
        if plan["action"] in ("train", "done"):
            assumed.setdefault(day, plan["session"]["key"])
    return days


LIGHTER_NOTE = ("⚠️ <b>Lighter today:</b> same exercises, one set fewer each, "
                "stop 3 reps before failure, no new weight records.")
PROGRESSION_NOTE = ("📈 <i>Progression: when you hit the top of the rep range on every set, "
                    "add 2.5 kg (upper) or 5 kg (lower) next time. Warm up 5 min + 2 lighter sets on the first lift. "
                    "Rest 2–3 min on big lifts, 60–90 s on the rest.</i>")


def exercise_list(session: dict) -> str:
    return "\n".join(f"• {name} — {scheme}" for name, scheme in session["exercises"])


def render_today(plan: dict, today: date) -> str:
    head = f"💪 <b>Today — {today.strftime('%a %d %b')}</b>  ({plan['done_this_week']}/{SESSIONS_PER_WEEK} this week)\n"
    r = plan["readiness"]
    body_signal = "\n".join(f"• {x}" for x in r["reasons"])
    if plan["action"] == "done":
        nxt = SESSIONS[(SESSION_KEYS.index(plan["session"]["key"]) + 1) % len(SESSIONS)]
        return (head + f"\n✅ Done today: <b>{plan['session']['name']}</b>. Nice work.\n\n"
                f"Next session: <b>{nxt['name']}</b>\n" + exercise_list(nxt))
    if plan["action"] in ("rest", "recover"):
        title = "😴 <b>Rest / active recovery</b>" if plan["action"] == "rest" else \
            "🛑 <b>Recovery day recommended</b> — your body data says hold back"
        why = plan["why"] if plan["action"] == "rest" else "Train again when readiness recovers."
        return (head + f"\n{title}\n<i>{why}</i>\n\n📟 <b>Body signals:</b>\n{body_signal}\n\n"
                + "\n".join(f"• {x}" for x in REST_DAY)
                + (f"\n\nNext session: <b>{plan['session']['name']}</b>" if plan["action"] == "rest" else
                   f"\n\nSession on hold: <b>{plan['session']['name']}</b> — do it tomorrow if you feel better."))
    lines = [head, f"🏋️ <b>{plan['session']['name']}</b>", f"<i>{plan['why']}</i>\n",
             f"📟 <b>Body signals:</b>\n{body_signal}\n"]
    if r["level"] == "lighter":
        lines.append(LIGHTER_NOTE + "\n")
    lines.append(exercise_list(plan["session"]))
    lines.append("\n" + STYLE_NOTE + "\n" + PROGRESSION_NOTE)
    return "\n".join(lines)


def render_week(days: list[tuple[date, dict]]) -> str:
    lines = ["📅 <b>Your week</b>"]
    for day, plan in days:
        name = plan["session"]["name"]
        if plan["action"] == "train":
            lines.append(f"\n🏋️ <b>{day.strftime('%a %d')} — {name}</b>\n{exercise_list(plan['session'])}")
        elif plan["action"] == "done":
            lines.append(f"\n✅ <b>{day.strftime('%a %d')}</b> — done: {name}")
        elif plan["action"] == "recover":
            lines.append(f"\n🛑 <b>{day.strftime('%a %d')}</b> — recovery (readiness low), {name} moves on")
        else:
            lines.append(f"\n😴 <b>{day.strftime('%a %d')}</b> — rest: walk + mobility")
    lines.append("\n" + STYLE_NOTE)
    lines.append("<i>Future days are a projection. Each morning's plan is rechecked against that day's "
                 "readiness, sleep and HRV.</i>")
    return "\n".join(lines)
