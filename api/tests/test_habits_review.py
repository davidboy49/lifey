"""Habit grid, quit card, weekly review and data tables."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.bot import store
from app.health import quality
from app.health import store as health_store
from app.journal import habits as h
from app.journal import review as r
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}


def put(day, category, tag, value=None, note=""):
    iso = day if isinstance(day, str) else day.isoformat()
    return store.log_activity(date_str=iso, category=category, tag=tag, note=note, value=value)


def log(day, category, tag, value=1.0, note="", ts=None):
    return {"id": 1, "date": day.isoformat(), "category": category, "tag": tag, "value": value, "note": note,
            "timestamp": ts or f"{day.isoformat()} 12:00:00", "occurred_at": "12:00"}


# ---------- pure: grid, strip, card ----------

def test_window_is_whole_weeks_ending_today():
    wed = date(2026, 10, 7)
    days = h.window(wed, 2)
    assert days[0].weekday() == 0 and days[0] == date(2026, 9, 28) and days[-1] == wed


def test_grid_keeps_unknown_none_and_logged_apart():
    d1, d2, d3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
    logs = [log(d1, "unholy_habit", "alcohol", 3), log(d2, "free_note", "note", None, "hello")]
    row = next(x for x in h.habit_grid(logs, [d1, d2, d3]) if x["tag"] == "alcohol")
    assert [c["state"] for c in row["cells"]] == ["logged", "none", "unknown"]
    assert row["cells"][0]["level"] == 3 and row["days"] == 1 and row["total"] == 3


def test_custom_habits_and_old_spellings_appear():
    d = date(2026, 10, 5)
    logs = [log(d, "unholy_habit", "sauna", 1), log(d, "unholy_habit", "late_screen_time", 1)]
    rows = {x["tag"]: x for x in h.habit_grid(logs, [d], {"sauna": ("Sauna", "sessions")})}
    assert rows["sauna"]["label"] == "Sauna" and rows["sauna"]["unit"] == "sessions" and rows["sauna"]["days"] == 1
    assert rows["late_screen"]["days"] == 1


def test_quit_strip_distinguishes_slip_clean_unchecked_unknown():
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(4)]
    logs = [log(days[0], "master", "master"), log(days[1], "master", "clean_day", 0),
            log(days[2], "free_note", "note", None, "x")]
    states = [c["state"] for c in h.quit_strip(logs, days)]
    assert states == ["slip", "clean", "unchecked", "unknown"]


def test_a_slip_costs_one_day_not_the_whole_run():
    today = date(2026, 10, 10)
    days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    logs = [log(today - timedelta(days=29), "master", "urge_resisted", 1),   # tracking starts 29 days ago
            log(today - timedelta(days=10), "master", "master", 1)]
    from app.bot import quit_tracker
    summary = quit_tracker.summarize(logs, today)
    card = h.quit_card(summary, h.quit_strip(logs, days), today)
    assert card["current_run"] == 10 and card["best_run"] == 19
    assert card["slips_30d"] == 1 and card["free_days_30"] == 29 and card["tracked_days_30"] == 30
    assert card["free_pct_30"] == 97


def test_card_is_none_before_tracking_starts():
    from app.bot import quit_tracker
    assert h.quit_card(quit_tracker.summarize([], date(2026, 10, 10)), [], date(2026, 10, 10)) is None


# ---------- API ----------

@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


def test_overview_has_the_pieces_the_page_needs(client):
    put(quality.today().isoformat(), "unholy_habit", "alcohol", value=2)
    body = client.get("/api/habits", params={"weeks": 5}).json()
    assert {"today", "days", "habits", "wellbeing", "quit", "catalog"} <= set(body)
    assert body["days"][0] <= body["today"] and body["days"][-1] == body["today"]
    assert len(body["quit"]["strip"]) == 30
    alcohol = next(x for x in body["habits"] if x["tag"] == "alcohol")
    assert alcohol["cells"][-1]["state"] == "logged"


def test_adding_a_custom_habit_makes_it_loggable_and_visible(client):
    r1 = client.post("/api/habits", json={"label": "Cold plunge", "unit": "sessions", "cue_if": "I wake up tired",
                                           "cue_then": "do a 2 minute cold shower"})
    assert r1.status_code == 201 and r1.json()["tag"] == "cold_plunge"
    assert client.post("/api/habits", json={"label": "Cold plunge"}).status_code == 409
    assert client.post("/api/habits", json={"label": "Alcohol"}).status_code == 409
    cat = client.get("/api/habits/catalog").json()
    mine = next(c for c in cat if c["tag"] == "cold_plunge")
    assert mine["builtin"] is False and mine["cue_if"] == "I wake up tired"
    assert client.post("/api/journal", json={"kind": "habit", "habit": "Cold plunge", "amount": 1}).status_code == 201
    grid = client.get("/api/habits").json()["habits"]
    assert next(x for x in grid if x["tag"] == "cold_plunge")["days"] == 1


def test_habits_can_be_edited_and_archived_but_builtins_cannot(client):
    client.post("/api/habits", json={"label": "Sauna"})
    assert client.patch("/api/habits/sauna", json={"cue_then": "drink water"}).status_code == 200
    assert client.patch("/api/habits/alcohol", json={"label": "x"}).status_code == 409
    assert client.patch("/api/habits/nope", json={"label": "x"}).status_code == 404
    assert client.patch("/api/habits/sauna", json={"archived": True}).status_code == 200
    assert "sauna" not in {c["tag"] for c in client.get("/api/habits/catalog").json()}


# ---------- weekly review ----------

def test_review_rejects_future_weeks_and_names_the_week(client):
    future = (quality.today() + timedelta(days=14)).isoformat()
    assert client.get("/api/review", params={"week": future}).status_code == 422
    body = client.get("/api/review").json()
    assert body["is_current"] is True and body["next_week"] is None
    assert body["label"].startswith(f"Week {date.fromisoformat(body['week_start']).isocalendar().week} ·")
    assert date.fromisoformat(body["week_start"]).weekday() == 0


def test_reflection_is_saved_per_week_and_last_weeks_plan_comes_back(client):
    this_week = r.monday(quality.today())
    last_week = this_week - timedelta(days=7)
    put = client.put(f"/api/review/{last_week}", json={"went_well": "Trained 3 times",
                                                      "plan_if": "it is 3pm and I want coffee",
                                                      "plan_then": "make tea and walk"})
    assert put.status_code == 200
    body = client.get("/api/review").json()
    assert body["last_plan"] == {"plan_if": "it is 3pm and I want coffee", "plan_then": "make tea and walk"}
    assert client.get("/api/review", params={"week": last_week.isoformat()}).json()["reflection"]["went_well"] == "Trained 3 times"
    assert client.put(f"/api/review/{this_week + timedelta(days=1)}", json={}).status_code == 422   # not a Monday
    assert client.put(f"/api/review/{this_week + timedelta(days=7)}", json={}).status_code == 422   # future


def _seed_nights(pg, pairs):
    """pairs: [(day, sleep_score)] where the score belongs to that morning."""
    for day, score in pairs:
        health_store.save_day(pg, day.isoformat(), {"sleep": {"dailySleepDTO": {
            "sleepTimeSeconds": 25000, "sleepScores": {"overall": {"value": score}}}}})
    pg.commit()


def test_few_nights_are_a_note_not_a_pattern(client, pg):
    today = quality.today()
    for i in (3, 5):
        put((today - timedelta(days=i)).isoformat(), "unholy_habit", "late_caffeine", 1)
    put(today.isoformat(), "unholy_habit", "late_caffeine", 1)
    put((today - timedelta(days=4)).isoformat(), "free_note", "note", None, "ordinary day")
    _seed_nights(pg, [(today - timedelta(days=2), 60), (today - timedelta(days=4), 62), (today - timedelta(days=3), 80)])
    body = client.get("/api/review").json()
    pattern = next(p for p in body["patterns"] if p["tag"] == "late_caffeine")
    assert pattern["enough"] is False and pattern["with_n"] == 2
    assert f"at least {r.MIN_NIGHTS} nights" in pattern["text"]


def test_enough_nights_become_a_pattern_with_the_caveat(client, pg):
    today = quality.today()
    pairs = []
    for i in range(2, 12):                    # 10 nights after a late coffee, low scores
        put((today - timedelta(days=i)).isoformat(), "unholy_habit", "late_caffeine", 1)
        pairs.append((today - timedelta(days=i - 1), 60))
    for i in range(12, 22):                   # 10 ordinary nights, higher scores
        put((today - timedelta(days=i)).isoformat(), "free_note", "note", None, "day")
        pairs.append((today - timedelta(days=i - 1), 80))
    put(today.isoformat(), "unholy_habit", "late_caffeine", 1)
    _seed_nights(pg, pairs)
    p = next(x for x in client.get("/api/review").json()["patterns"] if x["tag"] == "late_caffeine")
    assert p["enough"] is True and p["with_n"] == 10 and p["without_n"] == 10
    assert round(p["with_avg"]) == 60 and round(p["without_avg"]) == 80
    assert "not proof" in p["text"]


def test_days_with_no_entries_are_not_used_as_comparison_nights():
    today = date(2026, 10, 10)
    logs = [log(date(2026, 10, 3), "unholy_habit", "late_caffeine", 1)]
    daily = [{"date": "2026-10-04", "sleep_score": 55}, {"date": "2026-10-08", "sleep_score": 90}]
    out = r.pattern_candidates(logs, daily, ["late_caffeine"], today, {"late_caffeine": "Late caffeine"})
    assert out[0]["with_n"] == 1 and out[0]["without_n"] == 0       # 8 Oct has no entries: unknown, not "no habit"


def test_notes_of_the_week_skip_bot_boilerplate():
    logs = [log(date(2026, 10, 5), "free_note", "note", None, "Slept badly"),
            log(date(2026, 10, 5), "unholy_habit", "late_caffeine", 1, "Late Caffeine"),
            log(date(2026, 10, 6), "master", "urge_resisted", 1, "Bored, took a shower")]
    notes = r.notes_of_the_week(logs)
    assert [n["text"] for n in notes] == ["Slept badly", "Bored, took a shower"]


# ---------- data tables ----------

def test_dataset_list_and_table(client, pg):
    health_store.save_day(pg, "2026-10-09", {"summary": {"totalSteps": 5000, "restingHeartRate": 55},
                                            "sleep_error": "down"})
    pg.commit()
    names = {d["key"]: d["rows"] for d in client.get("/api/data").json()}
    assert names["daily_metrics"] == 1 and set(names) == {"daily_metrics", "activities", "journal", "habits", "checkins", "alerts", "sync_runs"}
    t = client.get("/api/data/daily_metrics").json()
    row = t["rows"][0]
    assert row["steps"] == 5000 and row["sleep_score"] is None            # a gap is null, never zero
    assert row["source"] == "partial"                                     # a failed fetch is visible in the row
    assert any(c["key"] == "synced_at" and c["hidden"] for c in t["columns"])
    assert client.get("/api/data/nope").status_code == 404
    assert client.get("/api/data/daily_metrics", params={"limit": 9999}).status_code == 422


def test_csv_export_defuses_spreadsheet_formulas(client):
    put(quality.today().isoformat(), "free_note", "note", None, "=HYPERLINK(\"http://evil\",\"x\")")
    resp = client.get("/api/data/journal/export.csv")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "'=HYPERLINK" in resp.text and ",=HYPERLINK" not in resp.text


def test_every_dataset_loads_and_exports_with_rows_present(client, pg):
    """One bad query must not hide behind the datasets that happen to work."""
    health_store.save_day(pg, "2026-10-09", {
        "summary": {"totalSteps": 5000, "restingHeartRate": 55},
        "activities": [{"activityId": 7, "activityName": "Morning run", "startTimeLocal": "2026-10-09 06:30:00",
                        "activityType": {"typeKey": "running"}, "duration": 1800, "distance": 5200, "calories": 300}]})
    pg.commit()
    put(quality.today(), "free_note", "note", None, "hello")
    put(quality.today(), "unholy_habit", "late_caffeine", 1.0, "espresso")
    store.save_checkin_answer(quality.today().isoformat(), "rpe", 6)
    pg.execute("INSERT INTO health.sync_runs(status, details) VALUES ('success', '{}'::jsonb)")
    pg.execute("""INSERT INTO journal.anomaly_alerts (date, severity, alert_type, message, algorithm_version)
                  VALUES ('2026-10-09', 'INFO', 'SPO2_MIN', 'm', 'observations-v1')""")
    pg.commit()
    for key in ("daily_metrics", "activities", "journal", "habits", "checkins", "alerts", "sync_runs"):
        t = client.get(f"/api/data/{key}")
        assert t.status_code == 200, f"{key}: {t.text[:120]}"
        assert t.json()["total"] >= 1 and len(t.json()["rows"]) >= 1, key
        assert client.get(f"/api/data/{key}/export.csv").status_code == 200, key
    run = client.get("/api/data/activities").json()["rows"][0]
    assert run["minutes"] == 30.0 and run["km"] == 5.2


def test_csv_text_window_and_habits_dataset(client, pg):
    from app import data_routes
    today = quality.today()
    put(today, "unholy_habit", "alcohol", 2.0, "two pints")
    put(today - timedelta(days=40), "unholy_habit", "alcohol", 1.0, "old")
    put(today, "free_note", "note", None, "not a habit")
    everything, n_all = data_routes.csv_text("habits")
    recent, n_recent = data_routes.csv_text("habits", 7)
    assert n_all == 2 and n_recent == 1
    assert "two pints" in recent and "old" not in recent and "not a habit" not in everything
    assert everything.splitlines()[0].startswith("ID,Date,Habit,Units")
