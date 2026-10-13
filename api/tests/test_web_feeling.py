"""Rating how you woke up from the web, the slip-window comparison, and reminder settings."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import reminders
from app.auth import service
from app.bot import store
from app.health import quality
from app.journal import habits as h
from app.main import app

ORIGIN = {"origin": "http://localhost:3000"}


@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


# ---------- pure: slip windows ----------

def test_feeling_by_run_groups_by_days_since_slip_and_withholds_thin_buckets():
    slips = {date(2026, 10, 1), date(2026, 10, 10)}
    feelings = {"2026-09-30": 2,                       # before any slip: no run to measure against, left out
                "2026-10-01": 1, "2026-10-02": 2, "2026-10-04": 3, "2026-10-09": 4,
                "2026-10-10": 1, "2026-10-12": 3}
    out = h.feeling_by_run(feelings, slips, needed=2)
    by = {r["label"]: r for r in out["rows"]}
    assert by["Slip day"]["n"] == 2 and by["Slip day"]["mean"] == 1.0 and by["Slip day"]["enough"]
    assert by["1 to 2 days after"]["n"] == 2          # Oct 2 (1 day) and Oct 12 (2 days)
    assert by["3 to 6 days"]["n"] == 1 and not by["3 to 6 days"]["enough"]
    assert by["1 to 2 weeks"]["n"] == 1                # Oct 9 is 8 days after Oct 1
    assert out["placed"] == 6 and out["rated_days"] == 7


def test_feeling_row_marks_unrated_days_unknown_not_neutral():
    days = [date(2026, 10, 1), date(2026, 10, 2)]
    row = h.feeling_row({"2026-10-02": 4}, days)
    assert row["cells"][0]["state"] == "unknown" and row["cells"][1]["value"] == 4
    assert row["average"] == 4 and row["count"] == 1


# ---------- API ----------

def test_rate_today_and_a_past_day_and_reject_the_future(client):
    today = quality.today()
    assert client.post("/api/habits/feeling", json={"rating": 4}).status_code == 200
    past = (today - timedelta(days=3)).isoformat()
    assert client.post("/api/habits/feeling", json={"rating": 2, "date": past}).json() == {"date": past, "rating": 2}
    assert client.post("/api/habits/feeling", json={"rating": 3, "date": (today + timedelta(days=1)).isoformat()}).status_code == 422
    assert client.post("/api/habits/feeling", json={"rating": 6}).status_code == 422
    assert client.post("/api/habits/feeling", json={"rating": 3, "date": "nope"}).status_code == 422
    body = client.get("/api/habits", params={"weeks": 2}).json()
    assert body["feeling"]["today"] == 4 and body["feeling"]["ratings"][past] == 2
    wake = next(r for r in body["wellbeing"] if r["tag"] == "wake")
    assert wake["count"] == 2


def test_reminder_settings_validate_and_persist(client):
    first = client.get("/api/settings/reminders").json()
    assert {r["key"] for r in first["reminders"]} == {"morning_feeling", "evening_checkin"}
    r = client.put("/api/settings/reminders", json={"morning_feeling": {"time": "07:30", "enabled": False}})
    assert r.status_code == 200
    mf = next(x for x in r.json()["reminders"] if x["key"] == "morning_feeling")
    assert mf == {"key": "morning_feeling", "label": "Morning feeling", "enabled": False, "time": "07:30"}
    assert client.put("/api/settings/reminders", json={"evening_checkin": {"time": "25:99"}}).status_code == 422
    assert client.put("/api/settings/reminders", json={}).status_code == 422
    again = client.get("/api/settings/reminders").json()["reminders"]
    assert next(x for x in again if x["key"] == "evening_checkin")["time"] == "22:00"   # untouched


def test_settings_require_a_session():
    c = TestClient(app, headers=ORIGIN)
    assert c.get("/api/settings/reminders").status_code == 401
    assert c.post("/api/habits/feeling", json={"rating": 3}).status_code == 401


# ---------- the scheduler's decision ----------

def at(hour, minute, day=(2026, 10, 13)):
    return datetime(*day, hour, minute, tzinfo=timezone(timedelta(hours=7)))


def test_due_fires_once_after_the_time_and_only_within_the_catch_up_window(pg):
    assert reminders.due(at(6, 54)) == []
    assert reminders.due(at(6, 55)) == ["morning_feeling"]
    assert reminders.due(at(9, 54)) == ["morning_feeling"]      # a restart within 3 h still catches up
    assert reminders.due(at(9, 56)) == []                       # too late: skipped, not sent at lunch
    reminders.mark_sent("morning_feeling", "2026-10-13")
    assert reminders.due(at(7, 10)) == []                       # already sent today
    assert reminders.due(at(22, 0)) == ["evening_checkin"]
    assert reminders.due(at(7, 10, day=(2026, 10, 14))) == ["morning_feeling"]   # next day


def test_switching_off_and_moving_the_time_are_respected(pg):
    reminders.save({"morning_feeling": {"enabled": False}})
    assert reminders.due(at(7, 0)) == []
    reminders.save({"morning_feeling": {"enabled": True, "time": "08:15"}})
    assert reminders.due(at(7, 0)) == []
    assert reminders.due(at(8, 15)) == ["morning_feeling"]
    with pytest.raises(ValueError):
        reminders.save({"morning_feeling": {"time": "8:15"}})
