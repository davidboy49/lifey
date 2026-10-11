"""Sleep tips checked against the person's own data, and a "see a doctor" panel.

Two firm limits, deliberately:
- Nothing here diagnoses. A wrist sensor cannot show insomnia, sleep apnea or any
  other disorder, and this module never claims otherwise. It lists numbers worth
  mentioning and the things only a clinician can assess.
- Matthew Walker's published tips are used as published, attributed to the book,
  and paraphrased. There is no persona, and nothing is said "as" him. Where Lifey
  has no data for a tip, the tip says so.
"""
from __future__ import annotations

from statistics import fmean

from .sleep_report import MEAN_WINDOW, kind, valid

CHECK_DAYS = 14
HABIT_LOOK_DAYS = 3          # days with the habit logged, out of the last 14, before it is called out
MIN_DAYS_WITH_ENTRIES = 7    # fewer days with entries than this and "none logged" says nothing

EXTRA_EVIDENCE = {
    "walker2017": {
        "cite": "Walker, 2017. Why We Sleep (appendix: twelve tips for healthy sleep)",
        "finding": "Practical sleep-hygiene advice: keep a regular schedule, limit late caffeine, nicotine and alcohol, avoid big late meals, keep the bedroom dark and cool, get daylight in the morning, and get up rather than lie awake.",
        "caveat": "The tips match mainstream sleep-hygiene guidance, which is why they are used. Some of the book's statistics (mortality and cancer figures) have been disputed by independent reviewers and are not used here.",
        "confidence": "moderate",
        "url": "https://en.wikipedia.org/wiki/Why_We_Sleep",
    },
    "guzey2019": {
        "cite": "Guzey, 2019. Critique of Why We Sleep",
        "finding": "An independent review argued that the book overstates the harms of short sleep and cites some claims its sources do not support, including its mortality and cancer figures.",
        "caveat": "One reviewer's analysis, with commentary from a Columbia statistician; the author has responded to some points. It concerns the book's statistics, not whether regular, adequate sleep is good for you.",
        "confidence": "moderate",
        "url": "https://guzey.com/books/why-we-sleep/",
    },
    "aasm_talk": {
        "cite": "AASM, patient guidance on talking to a doctor about sleep",
        "finding": "Keep a sleep diary or tracker record, and mention snoring, trouble falling or staying asleep, restless legs, excessive daytime sleepiness, and any medicines that may affect sleep.",
        "caveat": "General guidance for starting the conversation. It is not a checklist that diagnoses anything.",
        "confidence": "strong",
        "url": "https://aasm.org/doctors-are-sleeping-on-discussing-this-important-health-factor-with-patients",
    },
}


def _habit_state(label: str, days: int, entry_days: int, none_phrase: str) -> tuple[str, str]:
    if entry_days < MIN_DAYS_WITH_ENTRIES:
        return "unknown", f"Only {entry_days} of the last {CHECK_DAYS} days have journal entries, so this can't be judged."
    if days >= HABIT_LOOK_DAYS:
        return "look", f"{label} logged on {days} of the last {CHECK_DAYS} days."
    if days == 0:
        return "fine", none_phrase
    return "fine", f"{label} logged on {days} of the last {CHECK_DAYS} days."


def _tip(tid: str, topic: str, advice: str, state: str, data: str | None) -> dict:
    return {"id": tid, "topic": topic, "advice": advice, "state": state, "data": data}


def walker_tips(habit_days: dict[str, int], entry_days: int, reg: dict, awake_avg: float | None,
                training_days: int) -> list[dict]:
    """Walker's published tips (paraphrased), each with what Lifey can and cannot see."""
    none = "None logged in the last 14 days."
    out = []

    schedule = "Go to bed and get up at the same times every day, weekends included."
    if reg.get("enough"):
        out.append(_tip("schedule", "A fixed schedule", schedule, "look" if reg["irregular"] else "fine",
                        f"Wake time varies by about {reg['wake_sd_min']} min and bedtime by {reg['bed_sd_min']} min over {reg['nights']} nights."))
    else:
        out.append(_tip("schedule", "A fixed schedule", schedule, "unknown",
                        f"Only {reg.get('nights', 0)} nights with timing recorded; 7 are needed."))

    out.append(_tip("exercise", "Exercise, but not late", "Regular exercise helps sleep; finishing a few hours before bed is the usual advice.",
                    "not_measured",
                    f"{training_days} session{'' if training_days == 1 else 's'} logged in the last {CHECK_DAYS} days, but the time of day is not recorded."))

    state, data = _habit_state("Late caffeine or nicotine", max(habit_days.get("late_caffeine", 0), habit_days.get("nicotine", 0)),
                               entry_days, none)
    out.append(_tip("stimulants", "Caffeine and nicotine", "Avoid them in the afternoon and evening; caffeine can take hours to wear off.", state, data))

    state, data = _habit_state("Alcohol", habit_days.get("alcohol", 0), entry_days, none)
    out.append(_tip("alcohol", "Alcohol before bed", "Avoid alcohol close to bedtime; it can fragment sleep.", state, data))

    state, data = _habit_state("A late heavy meal", habit_days.get("late_meal", 0), entry_days, none)
    out.append(_tip("meals", "Large meals late", "Avoid big meals and lots of drink late in the evening.", state, data))

    out.append(_tip("medicines", "Medicines", "Some medicines delay or disrupt sleep. Ask your doctor or pharmacist about yours.",
                    "not_measured", None))
    out.append(_tip("naps", "Late naps", "Skip naps in the late afternoon; they can make it harder to fall asleep that night.",
                    "not_measured", "Garmin records naps, but Lifey does not analyse their timing yet."))
    out.append(_tip("wind_down", "Time to wind down", "Leave time before bed to relax, for example reading or quiet music.",
                    "not_measured", None))
    out.append(_tip("bath", "A warm bath", "A hot bath before bed may help, since the cool-down afterwards promotes sleepiness.",
                    "not_measured", None))

    state, data = _habit_state("Late screen time", habit_days.get("late_screen", 0), entry_days, none)
    out.append(_tip("bedroom", "A dark, cool, gadget-free bedroom", "Keep the bedroom dark and cool, and screens out of it.",
                    state, f"{data} Room temperature and light are not measured."))

    out.append(_tip("light", "Daylight", "Get outside in natural light, especially in the morning, and dim the lights in the evening.",
                    "not_measured", None))

    awake = "If you can't sleep, get up and do something quiet until you feel sleepy."
    if awake_avg is not None:
        out.append(_tip("awake", "Don't lie awake", awake, "info",
                        f"Garmin estimates about {awake_avg:.0f} min awake per night after you first fall asleep. That is an estimate, and time to fall asleep is not recorded."))
    else:
        out.append(_tip("awake", "Don't lie awake", awake, "not_measured", None))
    return out


def doctor_topics() -> list[str]:
    """From AASM's patient guidance on what to raise. Lifey cannot see any of these."""
    return [
        "Loud or frequent snoring, gasping or choking at night, or pauses in breathing someone has noticed.",
        "Trouble falling asleep or staying asleep that keeps coming back.",
        "An urge to move your legs in the evening or at night.",
        "Feeling very sleepy in the day, or falling asleep when you do not mean to, despite enough hours.",
        "A medicine you take that might affect your sleep.",
    ]


def doctor_flags(debt_info: dict, reg: dict, awake_avg: float | None) -> list[str]:
    """Numbers from the recording worth mentioning. They describe; they do not diagnose."""
    flags = []
    if debt_info["nights_counted"] and debt_info["nights_under_6"] >= 3:
        flags.append(f"{debt_info['nights_under_6']} of the last {debt_info['window']} nights were under 6 hours recorded.")
    if reg.get("enough") and reg["irregular"]:
        flags.append(f"Bedtime and wake time vary a lot (wake time by about {reg['wake_sd_min']} min).")
    if awake_avg is not None and awake_avg >= 45:
        flags.append(f"Garmin estimates about {awake_avg:.0f} minutes awake per night after falling asleep.")
    return flags


def awake_average(nights: list[dict], window: int = CHECK_DAYS) -> float | None:
    values = [n["awake_min"] for n in valid(nights[-window:]) if n.get("awake_min") is not None]
    return fmean(values) if len(values) >= 5 else None


def doctor_summary(nights: list[dict], reg: dict, awake_avg: float | None, as_of: str) -> str:
    """Plain text to bring to an appointment: what the watch recorded, and what it cannot know."""
    span = nights[-MEAN_WINDOW:]
    ok = valid(span)
    partial = sum(1 for n in span if kind(n) == "incomplete")
    lines = [
        f"Sleep summary from Lifey, last {MEAN_WINDOW} nights to {as_of}",
        "Source: Garmin wrist sensor. These are estimates, not a sleep study.",
        "",
        f"Nights recorded: {len(ok)} of {len(span)}" + (f" ({partial} partly recorded, left out)" if partial else ""),
    ]
    if ok:
        hours = [n["hours"] for n in ok]
        lines.append(f"Average sleep: {fmean(hours):.1f} h (shortest {min(hours):.1f} h, longest {max(hours):.1f} h)")
        lines.append(f"Nights under 6 h: {sum(1 for h in hours if h < 6)}; under 7 h: {sum(1 for h in hours if h < 7)}")
    if reg.get("enough"):
        lines.append(f"Usual bedtime {reg['usual_bed']} (varies by about {reg['bed_sd_min']} min); "
                     f"usual wake time {reg['usual_wake']} (varies by about {reg['wake_sd_min']} min)")
    if awake_avg is not None:
        lines.append(f"Average time awake during the night (Garmin estimate): {awake_avg:.0f} min")
    lines += ["", "Not measured by Lifey: snoring, breathing pauses, leg movements, daytime sleepiness, medicines."]
    return "\n".join(lines)
