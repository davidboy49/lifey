"""Weekly recap and action plan, generated on demand from verified facts.

vidhealth's generator only let a model *select* approved fact and action IDs;
the text itself was always `coaching.render`. That deterministic path is what
runs here, so recaps need no API key and never invent a claim. They are
regenerated whenever newer data exists, instead of waiting for someone to
press a button on a dashboard.
"""
from __future__ import annotations

from . import coaching
from . import store as db

DETERMINISTIC = "deterministic"


def _evidence(days: int) -> dict:
    return coaching.build_evidence(db.get_df(limit=max(1, days)), days)


def _latest_data_date() -> str | None:
    frame = db.get_df(limit=1)
    return None if frame.empty else str(frame.iloc[-1]["date"])


def generate_weekly_report(days: int = 7) -> dict | None:
    evidence = _evidence(days)
    if not evidence["facts"] or not evidence["period_end"]:
        return None
    text = coaching.render(evidence)
    db.save_coaching_report(evidence["period_end"], text, evidence, DETERMINISTIC, DETERMINISTIC)
    return db.get_latest_coaching_report()


def generate_action_plan(days: int = 7) -> dict | None:
    evidence = _evidence(days)
    if not evidence["facts"]:
        return None
    headline = "Recorded observations through " + evidence["period_end"]
    watchlist = ["Refresh source data and review the next recorded sleep and HRV observations."]
    db.save_action_plan(evidence["period_start"], evidence["period_end"], DETERMINISTIC, headline,
                        coaching.render(evidence), watchlist, evidence={**evidence, "validation": DETERMINISTIC})
    return db.get_latest_action_plan()


def ensure_weekly_report() -> dict | None:
    """The newest recap, regenerated first if the data has moved past it."""
    latest, data_date = db.get_latest_coaching_report(), _latest_data_date()
    if data_date and (latest is None or latest["date"] < data_date):
        return generate_weekly_report() or latest
    return latest


def ensure_action_plan() -> dict | None:
    latest, data_date = db.get_latest_action_plan(), _latest_data_date()
    if data_date and (latest is None or latest["period_end"] < data_date):
        return generate_action_plan() or latest
    return latest
