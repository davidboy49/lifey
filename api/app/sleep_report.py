"""Sleep debt, regularity and what sleep does in the person's own data.

A read-only report on top of data Lifey already keeps. It reuses the same
target (`SLEEP_TARGET_H`) and incomplete-recording threshold as the morning
briefing, so the numbers agree with what the bot says.

Principles:
- A night with no recording is unknown. It never counts as zero hours and
  never as a good night.
- A night under `MIN_PLAUSIBLE_SLEEP_H` is probably a partly recorded night
  (watch off, or only a nap captured). It is shown, but kept out of debt.
- A comparison needs `MIN_NIGHTS` nights in each group before it is called a
  pattern. Below that it is a note.
- Every study cited says what it was and how far it can be trusted.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import fmean, median, pstdev

from .journal import review as review_mod
from .ml.briefing import SLEEP_TARGET_H
from .ml.flags import MIN_PLAUSIBLE_SLEEP_H

MEAN_WINDOW = 28
DEBT_WINDOW = 14
MIN_NIGHTS = review_mod.MIN_NIGHTS
REGULARITY_FLAG_MIN = 60     # my default for "worth steadying", not a published cut-off
SHORT_NIGHT_H = 6.0

SQL = """
SELECT d.date, d.sleep_duration, d.sleep_score, d.hrv_last_night, d.resting_hr, d.steps, d.stress_avg,
       e.payload #>> '{dailySleepDTO,sleepStartTimestampLocal}' AS bed_ms,
       e.payload #>> '{dailySleepDTO,sleepEndTimestampLocal}'   AS wake_ms,
       e.payload #>> '{dailySleepDTO,awakeSleepSeconds}'        AS awake_s,
       e.payload #>> '{dailySleepDTO,nextSleepNeed,actual}'     AS need_next_min,
       e.payload #>> '{dailySleepDTO,nextSleepNeed,baseline}'   AS need_base_min,
       e.payload #>> '{dailySleepDTO,nextSleepNeed,feedback}'   AS need_feedback
FROM health.daily_metrics d
LEFT JOIN health.endpoint_state e ON e.date = d.date AND e.endpoint = 'sleep'
WHERE d.date BETWEEN %s AND %s
"""


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _wall(ms) -> datetime | None:
    """Garmin's "local" timestamps are epoch milliseconds whose UTC reading is the local wall clock."""
    v = _f(ms)
    return None if v is None else datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def load_nights(conn, end: date, days: int = 60) -> list[dict]:
    """One dict per calendar day ending at `end` (oldest first); gaps are present with hours=None."""
    start = end - timedelta(days=days - 1)
    rows = {r[0]: r for r in conn.execute(SQL, (start, end)).fetchall()}
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        r = rows.get(day)
        hours = None if r is None or r[1] is None else float(r[1]) / 3600.0
        bed, wake = (_wall(r[7]), _wall(r[8])) if r else (None, None)
        out.append({
            "date": day.isoformat(),
            "weekday": day.weekday(),
            "hours": hours,
            "score": None if r is None else _f(r[2]),
            "hrv": None if r is None else _f(r[3]),
            "resting_hr": None if r is None else _f(r[4]),
            "steps": None if r is None else _f(r[5]),
            "stress": None if r is None else _f(r[6]),
            "bed": bed.strftime("%H:%M") if bed else None,
            "wake": wake.strftime("%H:%M") if wake else None,
            # minutes after 18:00, so 23:30 and 00:30 sit next to each other
            "bed_min": None if bed is None else ((bed.hour * 60 + bed.minute) - 18 * 60) % (24 * 60),
            "wake_min": None if wake is None else wake.hour * 60 + wake.minute,
            "awake_min": None if r is None or _f(r[9]) is None else _f(r[9]) / 60.0,
            "garmin_need_next_h": None if r is None or _f(r[10]) is None else _f(r[10]) / 60.0,
            "garmin_need_base_h": None if r is None or _f(r[11]) is None else _f(r[11]) / 60.0,
            "garmin_need_feedback": None if r is None else r[12],
        })
    return out


def kind(n: dict) -> str:
    if n["hours"] is None:
        return "missing"
    return "incomplete" if n["hours"] < MIN_PLAUSIBLE_SLEEP_H else "recorded"


def valid(nights: list[dict]) -> list[dict]:
    return [n for n in nights if kind(n) == "recorded"]


def _last(nights: list[dict], count: int) -> list[dict]:
    return nights[-count:]


def _clock(minutes_after_18: float) -> str:
    m = round(minutes_after_18) + 18 * 60
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _sd(values: list[float]) -> float | None:
    return pstdev(values) if len(values) >= 2 else None


def debt(nights: list[dict], target: float = SLEEP_TARGET_H, window: int = DEBT_WINDOW) -> dict:
    """Shortfall against the target over the last `window` calendar nights.

    Only recorded nights count. Surplus does not cancel a shortfall: the lab
    evidence is that extra sleep one night does not fully repay an earlier one."""
    span = _last(nights, window)
    ok = valid(span)
    shortfalls = [max(0.0, target - n["hours"]) for n in ok]
    return {
        "window": window,
        "target_h": target,
        "hours": round(sum(shortfalls), 1),
        "nights_counted": len(ok),
        "nights_short": sum(1 for s in shortfalls if s > 0),
        "nights_under_6": sum(1 for n in ok if n["hours"] < SHORT_NIGHT_H),
        "nights_missing": sum(1 for n in span if kind(n) == "missing"),
        "nights_excluded": sum(1 for n in span if kind(n) == "incomplete"),
        "average_shortfall_h": round(fmean(shortfalls), 2) if shortfalls else None,
    }


def target_progress(nights: list[dict], target: float = SLEEP_TARGET_H) -> dict:
    span = _last(nights, MEAN_WINDOW)
    ok = valid(span)
    mean = fmean(n["hours"] for n in ok) if ok else None
    first_half = [n["hours"] for n in valid(span[: MEAN_WINDOW // 2])]
    second_half = [n["hours"] for n in valid(span[MEAN_WINDOW // 2:])]
    return {
        "window": MEAN_WINDOW,
        "target_h": target,
        "mean_h": None if mean is None else round(mean, 2),
        "gap_h": None if mean is None else round(target - mean, 2),
        "nights": len(ok),
        "met": None if mean is None else mean >= target,
        "nights_at_or_above": sum(1 for n in ok if n["hours"] >= target),
        "earlier_mean_h": round(fmean(first_half), 2) if len(first_half) >= 5 else None,
        "recent_mean_h": round(fmean(second_half), 2) if len(second_half) >= 5 else None,
    }


def regularity(nights: list[dict], window: int = DEBT_WINDOW) -> dict:
    ok = [n for n in valid(_last(nights, window)) if n["wake_min"] is not None and n["bed_min"] is not None]
    if len(ok) < 7:
        return {"nights": len(ok), "enough": False}
    wake_sd = _sd([n["wake_min"] for n in ok])
    bed_sd = _sd([n["bed_min"] for n in ok])
    usual_wake = median(n["wake_min"] for n in ok)
    usual_bed = median(n["bed_min"] for n in ok)
    return {
        "nights": len(ok), "enough": True,
        "wake_sd_min": round(wake_sd), "bed_sd_min": round(bed_sd),
        "usual_wake": f"{int(usual_wake) // 60:02d}:{int(usual_wake) % 60:02d}",
        "usual_bed": _clock(usual_bed),
        "flag_threshold_min": REGULARITY_FLAG_MIN,
        "irregular": wake_sd >= REGULARITY_FLAG_MIN or bed_sd >= REGULARITY_FLAG_MIN,
    }


def weekend_split(nights: list[dict]) -> dict:
    """Nights ending on a Saturday or Sunday morning against the rest (wake-up date)."""
    ok = valid(_last(nights, MEAN_WINDOW))
    wk = [n["hours"] for n in ok if n["weekday"] >= 5]
    rest = [n["hours"] for n in ok if n["weekday"] < 5]
    if len(wk) < 4 or len(rest) < 8:
        return {"enough": False, "weekend_n": len(wk), "weekday_n": len(rest)}
    return {"enough": True, "weekend_n": len(wk), "weekday_n": len(rest),
            "weekend_h": round(fmean(wk), 2), "weekday_h": round(fmean(rest), 2),
            "difference_h": round(fmean(wk) - fmean(rest), 2)}


def outcomes(nights: list[dict], mood_by_day: dict[str, float], trained_days: set[str],
             target: float = SLEEP_TARGET_H, feeling_by_day: dict[str, float] | None = None) -> dict:
    """How the days after short and adequate nights looked, in this person's own data.

    Same-morning physiology (HRV, resting heart rate) and how the day went (mood, steps,
    whether a session happened). Garmin readiness and Body Battery are left out on purpose:
    they are computed from the night's sleep, so they would only echo it."""
    ok = valid(nights)
    below = [n for n in ok if n["hours"] < target]
    above = [n for n in ok if n["hours"] >= target]

    def avg(group, key):
        vals = [n[key] for n in group if n.get(key) is not None]
        return (round(fmean(vals), 1), len(vals)) if vals else (None, 0)

    def mood(group):
        vals = [mood_by_day[n["date"]] for n in group if n["date"] in mood_by_day]
        return (round(fmean(vals), 2), len(vals)) if vals else (None, 0)

    def feeling(group):
        vals = [feeling_by_day[n["date"]] for n in group if feeling_by_day and n["date"] in feeling_by_day]
        return (round(fmean(vals), 2), len(vals)) if vals else (None, 0)

    def trained(group):
        return (round(100 * sum(1 for n in group if n["date"] in trained_days) / len(group)), len(group)) if group else (None, 0)

    rows = []
    for label, unit, fn_b, fn_a, better in [
        ("HRV that night", "ms", avg(below, "hrv"), avg(above, "hrv"), "higher"),
        ("Resting heart rate", "bpm", avg(below, "resting_hr"), avg(above, "resting_hr"), "lower"),
        ("Steps that day", "", avg(below, "steps"), avg(above, "steps"), "higher"),
        ("How you felt waking up (1 to 5)", "", feeling(below), feeling(above), "higher"),
        ("Mood that day (1 to 5)", "", mood(below), mood(above), "higher"),
        ("Days with a training session", "%", trained(below), trained(above), "higher"),
    ]:
        rows.append({"label": label, "unit": unit, "better": better,
                     "below": fn_b[0], "below_n": fn_b[1], "above": fn_a[0], "above_n": fn_a[1],
                     "enough": fn_b[1] >= MIN_NIGHTS and fn_a[1] >= MIN_NIGHTS})
    return {"target_h": target, "below_nights": len(below), "above_nights": len(above),
            "needed": MIN_NIGHTS, "rows": rows}


# ---- what the studies say (each claim limited to what the source reported) ----

EVIDENCE = {
    "watson2015": {
        "cite": "Watson et al., 2015. AASM and Sleep Research Society consensus statement",
        "finding": "Adults should sleep 7 or more hours per night on a regular basis; regularly sleeping less is linked to worse health and performance.",
        "caveat": "A consensus of expert panels reviewing the literature, not a single experiment. It sets a minimum for the population, not your personal need.",
        "confidence": "strong",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/",
    },
    "vandongen2003": {
        "cite": "Van Dongen et al., 2003. Sleep",
        "finding": "Over 14 nights, people kept to 6 hours in bed showed steadily growing lapses in attention, and were largely unaware of it.",
        "caveat": "48 healthy adults in a lab. The 'cumulative wakefulness' model behind it is the authors' and has been debated.",
        "confidence": "moderate",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12683469/",
    },
    "depner2019": {
        "cite": "Depner et al., 2019. Current Biology",
        "finding": "Weekend recovery sleep did not prevent metabolic dysregulation when short sleep resumed on weekdays; insulin sensitivity fell again.",
        "caveat": "A small lab study with sleep restricted to 5 hours. Reports differ on some group-level figures. Do not read it as a precise dose.",
        "confidence": "moderate",
        "url": "https://www.nih.gov/news-events/nih-research-matters/weekend-catch-cant-counter-chronic-sleep-deprivation",
    },
    "windred2024": {
        "cite": "Windred et al., 2024. Sleep (UK Biobank)",
        "finding": "In about 61,000 adults, more regular sleep timing was associated with lower all-cause mortality, and regularity predicted mortality more strongly than duration did.",
        "caveat": "Observational. It shows association, not that steadying your schedule will change your risk. The 60 minute flag here is my own default.",
        "confidence": "moderate",
        "url": "https://researchnow.flinders.edu.au/en/publications/sleep-regularity-is-a-stronger-predictor-of-mortality-risk-than-s/",
    },
    "mah2011": {
        "cite": "Mah et al., 2011. Sleep",
        "finding": "After 5 to 7 weeks of extending sleep by about 110 minutes a night, 11 collegiate basketball players ran a sprint faster (16.2 s to 15.5 s) and improved shooting accuracy by about 9%.",
        "caveat": "Eleven players and no control group. The players also gave up caffeine and alcohol during the study.",
        "confidence": "weak",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3119836/",
    },
    "drake2013": {
        "cite": "Drake et al., 2013. Journal of Clinical Sleep Medicine",
        "finding": "400 mg of caffeine taken 6 hours before bed cut measured sleep time by more than an hour, and people did not notice.",
        "caveat": "12 healthy sleepers and a single large dose. It supports avoiding caffeine for hours before bed, not an exact cut-off time.",
        "confidence": "weak",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3805807/",
    },
}

HABIT_EVIDENCE = {"late_caffeine": "drake2013"}


def suggestions(progress: dict, debt_info: dict, reg: dict, weekend: dict, need: dict | None,
                patterns: list[dict]) -> list[dict]:
    """Ranked, each tied to a number from the person's own data and to the evidence it rests on."""
    out: list[dict] = []
    target = progress["target_h"]

    if progress["gap_h"] is not None and progress["gap_h"] > 0.25:
        minutes = round(progress["gap_h"] * 60 / 5) * 5
        line = (f"Your {progress['window']}-day average is {progress['mean_h']:.1f} h against your {target:.1f} h target. "
                f"That is about {minutes} minutes more per night.")
        if reg.get("enough"):
            line += f" At your usual wake time of {reg['usual_wake']}, that means being asleep by roughly {_clock(_bed_for(reg, target))}."
        out.append({"id": "close_gap", "title": f"Add about {minutes} minutes a night", "detail": line,
                    "evidence": ["watson2015"]})

    if debt_info["nights_counted"] >= 7 and debt_info["hours"] >= 3:
        out.append({
            "id": "debt",
            "title": "Repay the shortfall in small steps, not one long sleep-in",
            "detail": (f"Over the last {debt_info['window']} nights you were {debt_info['hours']:.1f} h short of target "
                       f"({debt_info['nights_short']} of {debt_info['nights_counted']} recorded nights; "
                       f"{debt_info['nights_under_6']} under 6 h). In lab studies a weekend of extra sleep did not undo the effects of short weekdays, "
                       "and people did not feel the cost building up. Earlier bedtimes on several nights is the safer route."),
            "evidence": ["vandongen2003", "depner2019"],
        })

    if reg.get("enough") and reg["irregular"]:
        parts = []
        if reg["wake_sd_min"] >= REGULARITY_FLAG_MIN:
            parts.append(f"wake time varies by about {reg['wake_sd_min']} minutes")
        if reg["bed_sd_min"] >= REGULARITY_FLAG_MIN:
            parts.append(f"bedtime by about {reg['bed_sd_min']} minutes")
        out.append({"id": "regularity", "title": "Steady your timing", "detail":
                    f"Over {reg['nights']} nights your {' and '.join(parts)}. Pick one wake time and hold it within 30 minutes, "
                    "including weekends. Bedtime tends to follow.", "evidence": ["windred2024"]})

    if weekend.get("enough") and weekend["difference_h"] >= 1.0:
        out.append({"id": "weekend", "title": "Weekend catch-up is large", "detail":
                    f"You sleep {weekend['weekend_h']:.1f} h on weekend mornings against {weekend['weekday_h']:.1f} h on weekdays "
                    f"({weekend['difference_h']:.1f} h more). That pattern is the one lab work found does not fully repair weekday loss.",
                    "evidence": ["depner2019"]})

    if need and need.get("hours") and need["hours"] > target + 0.4:
        why = {"HIGHLY_INCREASED": "raised a lot", "INCREASED": "raised"}.get(need.get("feedback") or "", "raised")
        out.append({"id": "garmin_need", "title": f"Garmin puts tonight's need at {need['hours']:.1f} h", "detail":
                    f"Garmin's estimate (its own, not a measurement) is {need['hours']:.1f} h against a {need['baseline_h']:.1f} h baseline, "
                    f"{why} by recent training load and sleep history. It is higher than your {target:.1f} h target.",
                    "evidence": []})

    for p in patterns:
        if p["with_n"] < 1:
            continue
        item = {"id": f"habit_{p['tag']}", "title": f"{p['label']} and the night after", "detail": p["text"],
                "evidence": [HABIT_EVIDENCE[p["tag"]]] if p["tag"] in HABIT_EVIDENCE else [], "enough": p["enough"]}
        out.append(item)
    return out


def _bed_for(reg: dict, target: float) -> float:
    """Minutes after 18:00 at which to be asleep to reach `target` hours before the usual wake time."""
    h, m = (int(x) for x in reg["usual_wake"].split(":"))
    wake_after_18 = ((h * 60 + m) - 18 * 60) % (24 * 60)
    return (wake_after_18 - round(target * 60)) % (24 * 60)
