"""Templated morning briefing (Phase 2: facts and rules only, no LLM).

    python -m app.ml.briefing [--date YYYY-MM-DD] [--send]

Shape: at most 3 fact lines, then exactly one `Action:` line. Plain text, no emojis,
no exclamation marks. Every number comes from `ml.daily_flags`; a gap is stated, not guessed.

Not here yet, by design: forecasts and drivers (Phase 3), streak and check-in (Phase 4).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

from .. import db
from ..health import quality
from . import flags as flagmod
from .features import BY_KEY

# Owner-set target (2026-10-11): 28-day mean sleep of 7.0 h. Baseline at the time: 6.3 h.
SLEEP_TARGET_H = float(os.environ.get("SLEEP_TARGET_H", "7.0"))
NAMES = {"sleep_hours": "sleep", "sleep_score": "sleep score", "hrv": "HRV",
         "resting_hr": "resting HR", "bb_max": "Body Battery high", "stress_avg": "stress"}

PRIMARY = ("sleep_hours", "sleep_score", "hrv")
SECONDARY = ("resting_hr", "bb_max", "stress_avg")


def _fmt(key: str, value: float) -> str:
    m = BY_KEY[key]
    if key == "sleep_hours":
        return f"{value:.1f} h"
    return f"{value:.0f}" if m.unit == "/100" else f"{value:.0f} {m.unit}"


def _reading(f: dict) -> str:
    text = f"{NAMES[f['metric']]} {_fmt(f['metric'], f['value'])}"
    if f["baseline"] is not None and f["flag"] != "insufficient_baseline":
        text += f" (usual {_fmt(f['metric'], f['baseline'])})"
    return text


def render(flags: list[dict], crash: dict, day: date) -> str:
    by = {f["metric"]: f for f in flags}
    sleep_avg = by["sleep_hours"]["baseline"]
    have = [by[k] for k in PRIMARY if by[k]["value"] is not None]

    if not have:
        return "\n".join([
            f"No sleep, score or HRV recorded for {day.isoformat()}.",
            "Either the watch was not worn last night or Garmin has not synced yet.",
            "Action: open the Garmin app and sync the watch, then ask again.",
        ])

    lines = ["Last night: " + ", ".join(_reading(f) for f in have) + "."]
    reasons = crash["reasons"]
    if flagmod.INCOMPLETE in reasons:
        bb = by["bb_max"]["value"]
        seen = [f"sleep {_fmt('sleep_hours', by['sleep_hours']['value'])}"] if by["sleep_hours"]["value"] is not None else []
        if bb is not None:
            seen.append(f"Body Battery high {bb:.0f}")
        lines.append(f"Recording looks incomplete ({', '.join(seen)}); not treated as a crash night.")
        lines.append("Action: wear the watch tonight and sync in the morning; no recovery verdict from a partial night.")
        return "\n".join(lines)
    low = [k for k in PRIMARY + SECONDARY if by[k]["flag"] == "low" and BY_KEY[k].higher_is_better]
    high_bad = [k for k in SECONDARY if by[k]["flag"] == "high" and not BY_KEY[k].higher_is_better]
    short_baseline = [k for k in have if k["flag"] == "insufficient_baseline"]

    if crash["crash"]:
        sleep_names = " and ".join(NAMES[k] for k in reasons if k != "hrv")
        lines.append(f"Crash night: HRV 1.5 SD or more below your 28-day baseline, with {sleep_names} also down.")
    elif low or high_bad:
        names = ", ".join(NAMES[k] for k in low + high_bad)
        lines.append(f"Off your baseline: {names}.")
    elif short_baseline:
        lines.append("Baseline still building: fewer than 14 recorded days behind some of these.")
    else:
        lines.append("Everything you track is inside your normal range.")
        if sleep_avg is not None:
            lines[-1] += f" 28-day sleep average {sleep_avg:.1f} h against your {SLEEP_TARGET_H:.1f} h target."

    missing = [NAMES[k] for k in PRIMARY if by[k]["value"] is None]
    extras = [f"{NAMES[k]} {_fmt(k, by[k]['value'])} vs usual {_fmt(k, by[k]['baseline'])}"
              for k in high_bad + [k for k in low if k in SECONDARY]
              if by[k]["value"] is not None and by[k]["baseline"] is not None]
    if missing:
        lines.append("No reading for: " + ", ".join(missing) + ".")
    elif extras:
        lines.append("Also: " + "; ".join(extras) + ".")

    sleep_base = sleep_avg
    if crash["crash"] and sleep_base:
        action = f"easy day only, no hard session, and be in bed early enough for {SLEEP_TARGET_H:.1f} h tonight."
    elif high_bad and by["resting_hr"]["flag"] == "high" and by["resting_hr"]["baseline"]:
        action = (f"keep today easy; resting HR is {by['resting_hr']['value']:.0f} against "
                  f"{by['resting_hr']['baseline']:.0f} usual.")
    elif sleep_base and sleep_base < SLEEP_TARGET_H - 0.25:
        action = (f"train as planned and be in bed early enough for {SLEEP_TARGET_H:.1f} h tonight; "
                  f"your 28-day average is {sleep_base:.1f} h.")
    elif sleep_base:
        action = f"train as planned and hold bedtime; you are at your {SLEEP_TARGET_H:.1f} h sleep target."
    else:
        action = "log how today goes; there is not enough history for a baseline yet."
    lines.append("Action: " + action)
    return "\n".join(lines)


def build(conn, day: date | None = None) -> str:
    day = day or quality.today()
    results = flagmod.refresh(conn, end=day, days=7)
    flags, crash = results[-1]
    return render(flags, crash, day)


def send(text: str) -> None:
    """Deliver via the dedicated agent bot. Refuses unless token and chat id are both set."""
    token, chat = os.environ.get("AGENT_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("AGENT_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set to send")
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(request, timeout=20) as response:
        if not json.load(response).get("ok"):
            raise RuntimeError("Telegram rejected the message")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    with db.connect() as conn:
        text = build(conn, args.date)
    print(text)
    if args.send:
        try:
            send(text)
        except Exception as exc:  # noqa: BLE001 - never echo the token or URL
            print(f"Not sent: {type(exc).__name__}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
