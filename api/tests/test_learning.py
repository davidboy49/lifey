"""The learning thread: validation and counting (pure), then the focus lifecycle, the shelf, the review
block and the connector tool against real Postgres."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.bot import store
from app.connector import tools
from app.health import quality
from app.journal import learning, quests
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}
FOCUS = {"topic": "  Time-series   cross-validation ", "category": "tech",
         "outcome": "Explain expanding-window CV and run it on my sleep data.",
         "plan_if": "it is 20:00 on Tue", "plan_then": "I open the notebook for 30 minutes"}


# ---------- pure ----------

def test_validate_cleans_whitespace_and_derives_the_topic_key():
    out = learning.validate_focus(FOCUS)
    assert out["topic"] == "Time-series cross-validation" and out["topic_key"] == "time-series cross-validation"


@pytest.mark.parametrize("patch,message", [
    ({"topic": ""}, "topic is required"),
    ({"outcome": " "}, "outcome is required"),
    ({"category": "gardening"}, "Pick a category"),
    ({"topic": "x" * 81}, "at most 80"),
    ({"why": "y" * 201}, "at most 200"),
])
def test_validate_rejects_bad_input(patch, message):
    with pytest.raises(ValueError, match=message):
        learning.validate_focus({**FOCUS, **patch})


def test_every_category_the_owner_named_is_available():
    assert {"tech", "life", "sport", "money", "investing"} <= set(learning.CATEGORIES)


def test_renewal_is_due_when_the_focus_belongs_to_an_earlier_month():
    today = date(2026, 11, 3)
    assert learning.renewal(None, today) == "set"
    assert learning.renewal({"month": "2026-10-01"}, today) == "close"
    assert learning.renewal({"month": "2026-11-01"}, today) == "ok"


def log(day, minutes, tag="learning", category="unholy_habit"):
    return {"date": day.isoformat(), "category": category, "tag": tag, "value": minutes, "note": ""}


def test_sessions_count_entries_minutes_and_unknown_days():
    days = [date(2026, 10, 12) + timedelta(days=i) for i in range(4)]        # Mon..Thu
    logs = [log(days[0], 30), log(days[0], 15), log(days[2], 45, tag="alcohol"),
            {"date": days[2].isoformat(), "category": "free_note", "tag": "note", "value": None, "note": "x"}]
    s = learning.sessions(logs, "learning", days)
    assert (s["entries"], s["minutes"], s["days_practised"]) == (2, 45, 1)
    assert s["unknown_days"] == 2            # Tue and Thu have no entries at all, so they are not "missed"


def test_a_learning_quest_does_not_fail_a_rest_day_and_keeps_unknown_apart():
    week = [date(2026, 10, 5) + timedelta(days=i) for i in range(7)]
    row = {"tag": "learning", "cells": [{"date": d.isoformat(), "state": s} for d, s in
                                        zip(week, ["logged", "none", "unknown", "logged", "none", "none", "none"])]}
    q = quests.evaluate({"kind": "learning_sessions", "target": 3, "params": {"tag": "learning"}}, week, week[4],
                        grid_rows=[row], nights={}, trained=set(), habit_tags={"learning": "Learning"})
    assert [c["state"] for c in q["days"]] == ["pass", "rest", "unknown", "pass", "pending", "pending", "pending"]
    assert q["label"] == "3 learning sessions" and q["failed"] == 0 and q["status"] == "on_track"


def test_starter_shelf_has_links_and_caveats():
    assert len(learning.STARTER_SHELF) == 8
    for study in learning.STARTER_SHELF:
        assert study["url"].startswith("https://") and study["caveat"] and study["finding"]


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


def test_nothing_is_set_at_first(client):
    got = client.get("/api/learning").json()
    assert got["active"] is None and got["renewal"] == "set" and got["shelf"] == [] and len(got["starter"]) == 8


def test_the_learning_routes_need_a_session(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    assert TestClient(app, headers=ORIGIN).get("/api/learning").status_code == 401


def test_set_a_focus_creates_the_learning_habit_and_blocks_a_second(client):
    r = client.put("/api/learning/focus", json=FOCUS)
    assert r.status_code == 201
    focus = r.json()
    assert focus["status"] == "active" and focus["habit_tag"] == "learning" and focus["category"] == "tech"
    assert any(h["tag"] == "learning" and h["unit"] == "minutes" for h in client.get("/api/habits/catalog").json())
    again = client.put("/api/learning/focus", json={**FOCUS, "topic": "Spanish"})
    assert again.status_code == 409
    assert client.put("/api/learning/focus", json={**FOCUS, "category": "nope"}).status_code == 422


def test_invalid_focus_is_refused_with_a_readable_message(client):
    r = client.put("/api/learning/focus", json={**FOCUS, "outcome": ""})
    assert r.status_code == 422 and "outcome" in r.json()["detail"].lower()


def test_edit_the_active_focus(client):
    fid = client.put("/api/learning/focus", json=FOCUS).json()["id"]
    assert client.patch(f"/api/learning/focus/{fid}", json={"outcome": "Ship the CV notebook."}).status_code == 200
    assert client.get("/api/learning").json()["active"]["outcome"] == "Ship the CV notebook."
    assert client.patch(f"/api/learning/focus/{fid}", json={}).status_code == 422
    assert client.patch("/api/learning/focus/99999", json={"outcome": "x"}).status_code == 404


def test_close_and_continue_needs_a_fresh_outcome(client):
    fid = client.put("/api/learning/focus", json=FOCUS).json()["id"]
    body = {"result": "partly", "next_step": "continue"}
    assert client.post(f"/api/learning/focus/{fid}/close", json=body).status_code == 422
    assert client.get("/api/learning").json()["active"]["id"] == fid          # nothing was closed
    r = client.post(f"/api/learning/focus/{fid}/close", json={**body, "next_outcome": "Run it on 60 days of data."})
    assert r.status_code == 200 and r.json()["next"]["outcome"] == "Run it on 60 days of data."
    got = client.get("/api/learning").json()
    assert got["active"]["topic"] == "Time-series cross-validation" and got["active"]["id"] != fid
    assert got["history"][0]["result"] == "partly" and got["history"][0]["next_step"] == "continue"


def test_close_and_switch_or_pause_leaves_nothing_active(client):
    fid = client.put("/api/learning/focus", json=FOCUS).json()["id"]
    assert client.post(f"/api/learning/focus/{fid}/close", json={"result": "not_met", "next_step": "pause"}).status_code == 200
    got = client.get("/api/learning").json()
    assert got["active"] is None and got["renewal"] == "set" and got["history"][0]["result"] == "not_met"
    assert client.post(f"/api/learning/focus/{fid}/close", json={"result": "met", "next_step": "switch"}).status_code == 404
    assert client.put("/api/learning/focus", json={**FOCUS, "topic": "Spanish"}).status_code == 201


def test_close_refuses_unknown_words(client):
    fid = client.put("/api/learning/focus", json=FOCUS).json()["id"]
    assert client.post(f"/api/learning/focus/{fid}/close", json={"result": "great", "next_step": "pause"}).status_code == 422
    assert client.post(f"/api/learning/focus/{fid}/close", json={"result": "met", "next_step": "forever"}).status_code == 422


def test_shelf_keeps_a_study_with_its_link_and_the_retrieved_date(client):
    assert client.post("/api/learning/studies", json={"citation": "x", "url": "https://a.example/p", "finding": "y"}).status_code == 422
    client.put("/api/learning/focus", json=FOCUS)
    study = {"citation": "Roediger & Karpicke (2006)", "url": "https://doi.org/10.1111/j.1467-9280.2006.01693.x",
             "finding": "Testing beats restudying for delayed recall."}
    r = client.post("/api/learning/studies", json=study)
    assert r.status_code == 201
    assert client.post("/api/learning/studies", json=study).status_code == 409          # same link twice
    shelf = client.get("/api/learning").json()["shelf"]
    assert len(shelf) == 1 and shelf[0]["retrieved_on"] == quality.today().isoformat()
    assert client.delete(f"/api/learning/studies/{r.json()['id']}").status_code == 204
    assert client.delete(f"/api/learning/studies/{r.json()['id']}").status_code == 404
    assert client.get("/api/learning").json()["shelf"] == []


def test_shelf_refuses_links_that_are_not_web_addresses(client):
    client.put("/api/learning/focus", json=FOCUS)
    for url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x.example/a"):
        r = client.post("/api/learning/studies", json={"citation": "x", "url": url, "finding": "y"})
        assert r.status_code == 422


def test_review_block_counts_this_weeks_sessions_and_keeps_recall(client):
    today = quality.today()
    monday = quests.monday(today)
    client.put("/api/learning/focus", json=FOCUS)
    store.log_activity(date_str=monday.isoformat(), category="unholy_habit", tag="learning", note="", value=40.0)
    store.log_activity(date_str=monday.isoformat(), category="unholy_habit", tag="learning", note="", value=20.0)
    r = client.get("/api/review").json()["learning"]
    assert r["focus"]["topic"] == "Time-series cross-validation" and r["renewal"] == "ok"
    assert (r["week"]["entries"], r["week"]["minutes"], r["week"]["days_practised"]) == (2, 60, 1)

    body = {"went_well": "a", "got_in_way": "b", "learned": "c", "plan_if": "", "plan_then": "",
            "recall": "CV must never look at the future.", "learn_slot": "Tue and Thu 20:00"}
    assert client.put(f"/api/review/{monday.isoformat()}", json=body).status_code == 200
    saved = client.get("/api/review").json()["reflection"]
    assert saved["recall"] == "CV must never look at the future." and saved["learn_slot"] == "Tue and Thu 20:00"

    # An older client that does not send the new fields must not blank them.
    old = {k: body[k] for k in ("went_well", "got_in_way", "learned", "plan_if", "plan_then")}
    assert client.put(f"/api/review/{monday.isoformat()}", json=old).status_code == 200
    assert client.get("/api/review").json()["reflection"]["recall"] == "CV must never look at the future."

    nxt = client.get(f"/api/review?week={monday.isoformat()}").json()
    assert nxt["learning"]["last_recall"] is None            # last week has no recall yet


def test_last_weeks_recall_is_offered_for_spaced_retrieval(client):
    monday = quests.monday(quality.today())
    last = monday - timedelta(days=7)
    client.put(f"/api/review/{last.isoformat()}", json={"recall": "Spacing beats cramming.", "learn_slot": "Sat 09:00"})
    got = client.get("/api/review").json()["learning"]
    assert got["last_recall"] == "Spacing beats cramming." and got["last_slot"] == "Sat 09:00"


def test_a_learning_quest_round_trips(client):
    monday = quests.monday(quality.today())
    client.put("/api/learning/focus", json=FOCUS)
    body = {"kind": "learning_sessions", "target": 3, "params": {"tag": "learning"}}
    assert client.put(f"/api/quest/{monday.isoformat()}", json=body).status_code == 200
    assert client.get("/api/quest").json()["quest"]["label"] == "3 learning sessions"
    bad = {"kind": "learning_sessions", "target": 3, "params": {"tag": "nope"}}
    assert client.put(f"/api/quest/{monday.isoformat()}", json=bad).status_code == 422


# ---------- connector ----------

def test_connector_tool_shares_only_topic_outcome_and_counts(client):
    assert "No learning focus" in tools.learning()["note"]
    client.put("/api/learning/focus", json={**FOCUS, "why": "private reason"})
    client.put(f"/api/review/{quests.monday(quality.today()).isoformat()}",
               json={"recall": "my private recall text", "went_well": "private note"})
    store.log_activity(date_str=quality.today().isoformat(), category="unholy_habit", tag="learning",
                       note="private session note", value=25.0)
    got = tools.learning()
    assert got["focus"]["topic"] == "Time-series cross-validation"
    assert got["this_month"]["minutes"] == 25
    blob = str(got)
    for secret in ("private reason", "my private recall text", "private note", "private session note",
                   "open the notebook"):
        assert secret not in blob
