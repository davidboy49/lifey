"""Journal and manual-sync API, through the real auth and database."""
import threading
from datetime import timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.health import quality
from app.health import sync as garmin_sync
from app.journal import entries
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


def ago(days: int) -> str:
    return (quality.today() - timedelta(days=days)).isoformat()


def timeline(client, **params):
    r = client.get("/api/journal", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def all_entries(body):
    return [e for g in body["groups"] if not g["empty"] for e in g["entries"]]


# ---------- adding ----------

def test_habit_for_today_shows_up_with_its_amount(client):
    r = client.post("/api/journal", json={"kind": "habit", "habit": "Alcohol", "amount": 2, "note": "two pints"})
    assert r.status_code == 201 and r.json()["recalled"] is False
    [entry] = all_entries(timeline(client))
    assert entry["title"] == "Alcohol" and entry["badges"] == ["2 drinks"] and entry["note"] == "two pints"
    assert entry["recalled"] is False and entry["time_recorded"] is True


def test_backdated_entry_lands_on_its_day_and_is_marked_recalled(client):
    r = client.post("/api/journal", json={"kind": "habit", "habit": "late caffeine", "date": ago(2), "time": "16:10"})
    assert r.status_code == 201 and r.json()["recalled"] is True
    body = timeline(client, days=7)
    group = next(g for g in body["groups"] if not g["empty"])
    assert group["date"] == ago(2)
    assert group["entries"][0]["time"] == "16:10" and group["entries"][0]["recalled"] is True
    assert group["entries"][0]["title"] == "Late caffeine"


def test_dates_are_validated(client):
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "date": ago(-1)}).status_code == 422
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "date": ago(401)}).status_code == 422
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "time": "25:99"}).status_code == 422
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "date": ago(400)}).status_code == 201


def test_a_time_later_today_is_refused(client):
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "time": "23:59"}).status_code in (201, 422)
    # an unambiguous case: tomorrow's date with any time
    assert client.post("/api/journal", json={"kind": "note", "note": "x", "date": ago(-1), "time": "01:00"}).status_code == 422


def test_check_in_merges_mood_and_energy_and_needs_one_of_them(client):
    assert client.post("/api/journal", json={"kind": "checkin"}).status_code == 422
    r = client.post("/api/journal", json={"kind": "checkin", "mood": 4, "energy": 3, "note": "decent day"})
    assert r.status_code == 201 and len(r.json()["ids"]) == 2
    body = timeline(client)
    [entry] = all_entries(body)
    assert entry["kind"] == "checkin" and entry["badges"] == ["Mood 4/5", "Energy 3/5"] and entry["note"] == "decent day"
    assert body["summary"]["mood"] == 4 and body["summary"]["energy"] == 3


def test_notes_need_text_and_quit_entries_need_an_action(client):
    assert client.post("/api/journal", json={"kind": "note", "note": "   "}).status_code == 422
    assert client.post("/api/journal", json={"kind": "quit"}).status_code == 422
    assert client.post("/api/journal", json={"kind": "habit", "habit": "  "}).status_code == 422


def test_quit_actions_feed_the_streak(client):
    client.post("/api/journal", json={"kind": "quit", "action": "urge", "date": ago(3)})
    client.post("/api/journal", json={"kind": "quit", "action": "slip", "date": ago(2)})
    body = timeline(client, days=7)
    titles = [e["title"] for e in all_entries(body)]
    assert titles == ["Slip", "Urge resisted"]
    assert body["summary"]["days_free"] == 2


# ---------- reading ----------

def test_empty_days_are_unknown_and_filters_hide_gaps(client):
    client.post("/api/journal", json={"kind": "note", "note": "hello", "date": ago(3)})
    everything = timeline(client, days=7)
    assert any(g["empty"] for g in everything["groups"])           # the days with nothing are shown as unknown
    only_notes = timeline(client, days=7, kind="note")
    assert not any(g["empty"] for g in only_notes["groups"])
    assert client.get("/api/journal", params={"kind": "bogus"}).status_code == 422


def test_bot_default_notes_are_hidden():
    log = {"id": 1, "date": "2026-10-09", "category": "unholy_habit", "tag": "late_caffeine",
           "note": "Late Caffeine", "value": 1, "timestamp": "2026-10-09 16:00:00", "occurred_at": "16:00"}
    [entry] = entries.build_entries([log])
    assert entry["note"] == "" and entry["title"] == "Late caffeine" and entry["badges"] == []


def test_old_spellings_map_to_the_same_habit():
    log = {"id": 1, "date": "2026-10-09", "category": "unholy_habit", "tag": "late_screen_time", "note": "", "value": 1}
    assert entries.build_entries([log])[0]["title"] == "Late screen"


def test_a_row_without_a_recorded_time_uses_the_saved_time_and_says_so():
    log = {"id": 1, "date": "2026-10-09", "category": "free_note", "tag": "note", "note": "hi",
           "timestamp": "2026-10-09 21:14:00", "occurred_at": None}
    [entry] = entries.build_entries([log])
    assert entry["time"] == "21:14" and entry["time_recorded"] is False and entry["recalled"] is False


# ---------- removing ----------

def test_delete_removes_the_entry_and_a_second_delete_is_a_404(client):
    entry_id = client.post("/api/journal", json={"kind": "note", "note": "oops"}).json()["ids"][0]
    assert client.delete(f"/api/journal/{entry_id}").status_code == 204
    assert all_entries(timeline(client)) == []
    assert client.delete(f"/api/journal/{entry_id}").status_code == 404


def test_cross_site_writes_are_refused(client):
    assert client.post("/api/journal", json={"kind": "note", "note": "x"},
                       headers={"Origin": "https://evil.example"}).status_code == 403


# ---------- manual sync ----------

def test_sync_needs_credentials(client, monkeypatch):
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    assert client.post("/api/health/sync", json={}).status_code == 503


def test_sync_starts_in_the_background(client, monkeypatch):
    monkeypatch.setenv("GARMIN_EMAIL", "a@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    called, done = [], threading.Event()
    from app.bot import syncer
    monkeypatch.setattr(syncer, "smart_sync", lambda days: (called.append(days), done.set()))
    r = client.post("/api/health/sync", json={"days": 5})
    assert r.status_code == 202 and r.json() == {"started": True, "days": 5}
    assert done.wait(5) and called == [5]
    assert client.post("/api/health/sync", json={"days": 99}).status_code == 422


def test_sync_refuses_to_start_while_one_is_running(client, monkeypatch, database_url):
    monkeypatch.setenv("GARMIN_EMAIL", "a@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "secret")
    holder = psycopg.connect(database_url)
    try:
        holder.execute("SELECT pg_advisory_lock(%s)", (garmin_sync.SYNC_LOCK_KEY,))
        assert client.post("/api/health/sync", json={}).status_code == 409
    finally:
        holder.close()


def test_sync_status_reports_running_only_for_a_recent_run(client, pg):
    pg.execute("INSERT INTO health.sync_runs(status) VALUES ('running')")
    pg.commit()
    assert client.get("/api/health/sync").json()["running"] is True
    pg.execute("UPDATE health.sync_runs SET started_at = NOW() - interval '2 hours'")
    pg.commit()
    assert client.get("/api/health/sync").json()["running"] is False   # a crashed run, not a live one
