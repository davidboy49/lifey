"""Comeback episodes, weekly quests and On this day.

The first half is pure (no database). The second half goes through the API against real Postgres,
like the rest of the suite.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.bot import store
from app.health import quality
from app.journal import habits as h
from app.journal import memories, quests
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}


def strip(states: str) -> list[dict]:
    """'cxs?' -> clean, unchecked, slip, unknown cells on consecutive days."""
    names = {"c": "clean", "u": "unchecked", "s": "slip", "?": "unknown"}
    start = date(2026, 9, 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "state": names[ch]} for i, ch in enumerate(states)]


# ---------- comeback ----------

def test_no_slips_means_nothing_to_say():
    c = h.comeback(strip("cccc"))
    assert c["episodes"] == 0 and c["next_day"] == 0 and h.comeback_text(c) is None


def test_a_single_slip_that_ends_the_next_day_counts_as_bounced_back():
    c = h.comeback(strip("ccscc"))
    assert (c["episodes"], c["next_day"], c["longest"], c["ongoing"]) == (1, 1, 1, False)
    assert h.comeback_text(c) == "1 of 1 slip in the last 5 days ended the next day."


def test_consecutive_slip_days_are_one_longer_episode():
    c = h.comeback(strip("ssscsc"))
    assert c["episodes"] == 2 and c["next_day"] == 1 and c["longest"] == 3
    assert "Longest was 3 days in a row." in h.comeback_text(c)


def test_a_slip_today_is_ongoing_and_not_counted_as_recovered():
    c = h.comeback(strip("ccs"))
    assert c["ongoing"] and c["next_day"] == 0
    assert "Slip today" in h.comeback_text(c)


def test_a_day_with_no_entries_after_a_slip_is_not_read_as_recovery():
    c = h.comeback(strip("cs?c"))
    assert c["episodes"] == 1 and c["next_day"] == 0 and c["unknown"] == 1
    assert "not counted either way" in h.comeback_text(c)


# ---------- quests ----------

TAGS = {"alcohol": "Alcohol", "late_caffeine": "Late caffeine"}
WEEK = [date(2026, 10, 5) + timedelta(days=i) for i in range(7)]      # Mon 5 Oct .. Sun 11 Oct


def night(day: date, hours: float | None, bed: str | None = None) -> dict:
    bed_min = None
    if bed:
        hh, mm = (int(x) for x in bed.split(":"))
        bed_min = (hh * 60 + mm - 18 * 60) % (24 * 60)
    return {"date": day.isoformat(), "hours": hours, "bed_min": bed_min}


def grid_row(tag: str, states: list[str]) -> dict:
    return {"tag": tag, "cells": [{"date": d.isoformat(), "state": s} for d, s in zip(WEEK, states)]}


def run(kind: str, target: int, params: dict, today: date, **data) -> dict:
    quest = {"kind": kind, "target": target, "params": params}
    return quests.evaluate(quest, WEEK, today, grid_rows=data.get("grid_rows", []), nights=data.get("nights", {}),
                           trained=data.get("trained", set()), habit_tags=TAGS)


def test_habit_free_counts_only_days_that_are_over_and_logged():
    states = ["none", "none", "logged", "unknown", "none", "unknown", "unknown"]
    q = run("habit_free", 4, {"tag": "alcohol"}, today=WEEK[4], grid_rows=[grid_row("alcohol", states)])
    # Mon, Tue pass; Wed fail; Thu unknown; Fri (today) and the weekend are still pending.
    assert (q["passed"], q["failed"], q["unknown"], q["pending"]) == (2, 1, 1, 3)
    assert q["status"] == "on_track"
    assert q["label"] == "No alcohol on 4 of 7 days"


def test_status_is_at_risk_when_every_remaining_day_has_to_count():
    states = ["none", "logged", "logged", "none", "unknown", "unknown", "unknown"]
    q = run("habit_free", 4, {"tag": "alcohol"}, today=WEEK[4], grid_rows=[grid_row("alcohol", states)])
    assert q["passed"] == 2 and q["pending"] == 3 and q["status"] == "on_track"
    states = ["none", "logged", "logged", "logged", "unknown", "unknown", "unknown"]
    q = run("habit_free", 4, {"tag": "alcohol"}, today=WEEK[4], grid_rows=[grid_row("alcohol", states)])
    assert q["passed"] == 1 and q["pending"] == 3 and q["status"] == "at_risk"


def test_a_week_that_can_no_longer_reach_the_target_is_missed():
    states = ["logged"] * 7
    q = run("habit_free", 3, {"tag": "alcohol"}, today=WEEK[6] + timedelta(days=1), grid_rows=[grid_row("alcohol", states)])
    assert q["status"] == "missed" and q["pending"] == 0


def test_sleep_hours_ignores_incomplete_and_missing_nights():
    nights = {WEEK[0]: night(WEEK[0], 7.4), WEEK[1]: night(WEEK[1], 6.1), WEEK[2]: night(WEEK[2], 1.5),
              WEEK[3]: night(WEEK[3], None)}
    q = run("sleep_hours", 3, {"hours": 7.0}, today=WEEK[4], nights=nights)
    assert [c["state"] for c in q["days"][:5]] == ["pass", "fail", "unknown", "unknown", "pending"]
    assert q["label"] == "7 hours or more on 3 nights"


def test_a_night_not_synced_yet_is_pending_not_unknown():
    q = run("sleep_hours", 3, {"hours": 7.0}, today=WEEK[2], nights={WEEK[0]: night(WEEK[0], 7.5)})
    assert q["days"][2]["state"] == "pending" and q["days"][1]["state"] == "unknown"


def test_bed_before_handles_bedtimes_after_midnight():
    nights = {WEEK[0]: night(WEEK[0], 7.0, "22:40"), WEEK[1]: night(WEEK[1], 7.0, "23:30"),
              WEEK[2]: night(WEEK[2], 7.0, "00:20")}
    q = run("bed_before", 2, {"time": "23:00"}, today=WEEK[3], nights=nights)
    assert [c["state"] for c in q["days"][:3]] == ["pass", "fail", "fail"]


def test_training_counts_sessions_and_a_rest_day_is_not_a_failure():
    q = run("training", 2, {}, today=WEEK[3], trained={WEEK[0], WEEK[2]})
    assert [c["state"] for c in q["days"][:4]] == ["pass", "rest", "pass", "pending"]
    assert q["status"] == "met" and q["failed"] == 0


def test_validation_rejects_bad_input():
    with pytest.raises(ValueError):
        quests.validate("habit_free", 3, {"tag": "nope"}, TAGS)
    with pytest.raises(ValueError):
        quests.validate("sleep_hours", 3, {"hours": 4.0}, TAGS)
    with pytest.raises(ValueError):
        quests.validate("bed_before", 3, {"time": "03:00"}, TAGS)
    with pytest.raises(ValueError):
        quests.validate("sleep_hours", 9, {"hours": 7.0}, TAGS)
    with pytest.raises(ValueError):
        quests.validate("made_up", 3, {}, TAGS)
    assert quests.validate("training", 4, {"ignored": 1}, TAGS) == {}


def test_render_is_plain_text():
    q = run("training", 2, {}, today=WEEK[3], trained={WEEK[0]})
    text = quests.render(q)
    assert "Done 1 of 2" in text and "On track." in text and "!" not in text


# ---------- on this day ----------

def test_months_back_clamps_to_the_month_length():
    assert memories.months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert memories.months_back(date(2026, 10, 14), 12) == date(2025, 10, 14)
    assert memories.months_back(date(2026, 1, 15), 3) == date(2025, 10, 15)
    assert memories.months_back(date(2028, 2, 29), 12) == date(2027, 2, 28)


def entry(id_, note, category="free_note", tag="note", day="2025-10-14", occurred="19:42"):
    return {"id": id_, "date": day, "category": category, "tag": tag, "note": note, "value": None,
            "occurred_at": occurred, "timestamp": f"{day} 20:00:00"}


def test_a_photo_beats_a_longer_note_and_habit_taps_are_not_memories():
    logs = [entry(1, "A long note about the day that goes on"), entry(2, "short"),
            entry(3, "1 standard drink", category="unholy_habit", tag="alcohol")]
    files = {2: [{"id": 9, "filename": "a.jpg", "has_thumb": True}]}
    best = memories.pick(logs, files)
    assert best["log_id"] == 2 and best["attachment"]["id"] == 9


def test_a_day_with_nothing_written_has_no_memory():
    assert memories.pick([entry(1, "", category="unholy_habit", tag="alcohol"), entry(2, "Late caffeine")], {}) is None
    assert memories.pick([entry(1, "Late caffeine")], {}) is None


def test_best_prefers_a_photo_then_the_nearest():
    a = {"label": "A month ago", "attachment": None}
    b = {"label": "A year ago", "attachment": {"id": 1}}
    assert memories.best([a, b]) is b and memories.best([a]) is a and memories.best([]) is None


# ---------- through the API ----------

@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


def test_quest_round_trip(client):
    this_monday = quests.monday(quality.today())
    assert client.get("/api/quest").json()["quest"] is None
    body = {"kind": "habit_free", "target": 5, "params": {"tag": "alcohol"}}
    assert client.put(f"/api/quest/{this_monday.isoformat()}", json=body).status_code == 200
    got = client.get("/api/quest").json()
    assert got["quest"]["label"] == "No alcohol on 5 of 7 days" and got["editable"] is True
    assert client.delete(f"/api/quest/{this_monday.isoformat()}").status_code == 204
    assert client.get("/api/quest").json()["quest"] is None


def test_quest_only_for_this_week_or_next(client):
    this_monday = quests.monday(quality.today())
    body = {"kind": "training", "target": 3, "params": {}}
    assert client.put(f"/api/quest/{(this_monday + timedelta(days=7)).isoformat()}", json=body).status_code == 200
    assert client.put(f"/api/quest/{(this_monday - timedelta(days=7)).isoformat()}", json=body).status_code == 422
    assert client.put(f"/api/quest/{(this_monday + timedelta(days=14)).isoformat()}", json=body).status_code == 422
    assert client.put(f"/api/quest/{(this_monday + timedelta(days=1)).isoformat()}", json=body).status_code == 422
    bad = {"kind": "habit_free", "target": 3, "params": {"tag": "nope"}}
    assert client.put(f"/api/quest/{this_monday.isoformat()}", json=bad).status_code == 422


def test_quest_shows_last_weeks_plan_as_the_reason(client):
    this_monday = quests.monday(quality.today())
    last = this_monday - timedelta(days=7)
    client.put(f"/api/review/{last.isoformat()}", json={"plan_if": "it is 22:30", "plan_then": "phone goes away"})
    assert client.get("/api/quest").json()["plan"] == {"plan_if": "it is 22:30", "plan_then": "phone goes away"}


def test_habits_overview_carries_the_comeback(client):
    today = quality.today()
    store.log_activity(date_str=(today - timedelta(days=3)).isoformat(), category="master", tag="master",
                       note="", value=1.0)
    store.log_activity(date_str=(today - timedelta(days=2)).isoformat(), category="free_note", tag="note",
                       note="a normal day", value=None)
    back = client.get("/api/habits").json()["quit"]["comeback"]
    assert back["episodes"] == 1 and back["next_day"] == 1 and "ended the next day" in back["text"]


def test_memories_endpoint_returns_a_note_from_a_month_ago(client):
    today = quality.today()
    day = memories.months_back(today, 1)
    store.log_activity(date_str=day.isoformat(), category="free_note", tag="note",
                       note="Walked by the river", value=None, occurred_at="18:05")
    got = client.get("/api/journal/memories").json()["memories"]
    assert got and got[0]["label"] == "A month ago" and got[0]["note"] == "Walked by the river"
    assert got[0]["time"] == "18:05" and got[0]["attachment"] is None
