"""Connector writes: the consent page decides the scope, writes are small, audited and undoable, and
anything that changes a commitment waits in the inbox."""
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import service
from app.connector import writes
from app.health import quality
from app.journal import learning, proposals, quests, repo
from app.main import app
from test_connector import (CALLBACK, CHALLENGE, VERIFIER, app_client, authorize, call, register, rpc)  # noqa: F401

ORIGIN = {"Origin": "http://localhost:3000"}
STUDY = {"citation": "Roediger & Karpicke (2006), Psychological Science",
         "url": "https://doi.org/10.1111/j.1467-9280.2006.01693.x",
         "finding": "Taking a test on material improved delayed recall more than restudying it."}


def tokens(c, write: bool):
    client_id = register(c).json()["client_id"]
    form = {"request": authorize(c, client_id), "username": "david", "password": "correct horse battery",
            "action": "allow"}
    if write:
        form["write"] = "1"
    done = c.post("/oauth/login", data=form)
    assert done.status_code == 303
    code = parse_qs(urlparse(done.headers["location"]).query)["code"][0]
    tok = c.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK,
                                 "client_id": client_id, "code_verifier": VERIFIER})
    assert tok.status_code == 200, tok.text
    return tok.json()


def raw_call(c, token, name, arguments=None):
    r = rpc(c, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def audit_rows(pg):
    with db.connect() as conn:
        return conn.execute("SELECT tool, outcome, ref_kind FROM journal.connector_audit ORDER BY id").fetchall()


def set_focus():
    learning.ensure_habit()
    return repo.create_focus(learning.month_start(quality.today()), {
        **learning.validate_focus({"topic": "Index fund investing", "category": "investing",
                                   "outcome": "Pick one fund for my plan."}), "habit_tag": "learning"})


# ---------- consent and scope ----------

def test_consent_page_offers_capture_and_says_what_it_does_not_allow(app_client):
    client_id = register(app_client).json()["client_id"]
    page = app_client.get("/oauth/login", params={"request": authorize(app_client, client_id)}).text
    assert 'name="write"' in page and "log learning sessions" in page
    assert "delete or edit anything else" in page and "notes and reflections" in page


def test_by_default_the_connection_is_read_only(app_client, pg):
    tok = tokens(app_client, write=False)
    assert tok["scope"] == "lifey:read"
    result = raw_call(app_client, tok["access_token"], "lifey_log_learning_session", {"minutes": 30})
    assert result["isError"] and "read-only" in result["content"][0]["text"]
    assert audit_rows(pg) == []
    # reading still works
    assert call(app_client, tok["access_token"], "lifey_learning")["focus"] is None


def test_ticking_the_box_grants_write_and_the_tools_are_listed(app_client):
    tok = tokens(app_client, write=True)
    assert set(tok["scope"].split()) == {"lifey:read", "lifey:write"}
    names = {t["name"] for t in rpc(app_client, tok["access_token"], "tools/list", id_=2).json()["result"]["tools"]}
    assert {"lifey_log_learning_session", "lifey_propose_study", "lifey_propose_focus",
            "lifey_propose_quest"} <= names
    # No tool for what must stay yours.
    assert not {n for n in names if any(w in n for w in ("close", "reflection", "recall", "delete", "note", "habit"))
                } - {"lifey_habits"}


def test_the_client_cannot_widen_what_the_owner_granted(app_client):
    client_id = app_client.post("/register", json={
        "redirect_uris": [CALLBACK], "client_name": "Claude", "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "scope": "lifey:read lifey:write"}).json()["client_id"]
    r = app_client.get("/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK, "code_challenge": CHALLENGE,
        "code_challenge_method": "S256", "state": "s", "scope": "lifey:read lifey:write",
        "resource": "https://lifey.test/mcp"})
    request_id = parse_qs(urlparse(r.headers["location"]).query)["request"][0]
    done = app_client.post("/oauth/login", data={"request": request_id, "username": "david",
                                                 "password": "correct horse battery", "action": "allow"})
    code = parse_qs(urlparse(done.headers["location"]).query)["code"][0]
    tok = app_client.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK,
                                          "client_id": client_id, "code_verifier": VERIFIER}).json()
    assert tok["scope"] == "lifey:read"                      # asked for write, owner did not tick it


# ---------- logging a session ----------

def test_a_session_is_logged_as_the_learning_habit_and_audited(app_client, pg):
    tok = tokens(app_client, write=True)["access_token"]
    got = call(app_client, tok, "lifey_log_learning_session", {"minutes": 35, "request_id": "r1"})
    assert got["logged"] is True and got["minutes"] == 35
    with db.connect() as conn:
        row = conn.execute("SELECT category, tag, value, note FROM journal.activity_logs WHERE tag='learning'").fetchone()
    assert row == ("unholy_habit", "learning", 35.0, "")
    assert audit_rows(pg) == [("lifey_log_learning_session", "ok", "activity_log")]


def test_the_same_request_id_is_not_logged_twice(pg):
    first = writes.log_learning_session("c", 30, None, "same")
    again = writes.log_learning_session("c", 30, None, "same")
    assert first["logged"] and again == {"logged": False, **{k: again[k] for k in ("duplicate", "audit_id", "summary")}}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal.activity_logs WHERE tag='learning'").fetchone()[0] == 1


@pytest.mark.parametrize("minutes,day,message", [
    (0, None, "between 1 and 600"), (601, None, "between 1 and 600"), ("lots", None, "must be a number"),
    (30, "2999-01-01", "not happened yet"), (30, "not-a-date", "Use a date"),
])
def test_bad_sessions_are_refused_and_nothing_is_written(pg, minutes, day, message):
    with pytest.raises(writes.Refused, match=message):
        writes.log_learning_session("c", minutes, day, None)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal.activity_logs WHERE tag='learning'").fetchone()[0] == 0


def test_only_the_last_week_can_be_backfilled(pg):
    old = (quality.today() - timedelta(days=8)).isoformat()
    with pytest.raises(writes.Refused, match="last 7 days"):
        writes.log_learning_session("c", 30, old, None)
    assert writes.log_learning_session("c", 30, (quality.today() - timedelta(days=7)).isoformat(), None)["logged"]


def test_writes_are_rate_limited(pg, monkeypatch):
    monkeypatch.setattr(writes, "RATE_PER_HOUR", 2)
    writes.log_learning_session("c", 10, None, None)
    writes.log_learning_session("c", 10, None, None)
    with pytest.raises(writes.Refused, match="limit"):
        writes.log_learning_session("c", 10, None, None)
    assert audit_rows(pg)[-1][1] == "refused"


# ---------- proposals ----------

def test_a_proposed_study_waits_and_only_lands_when_accepted(pg):
    set_focus()
    out = writes.propose_study("c", request_id="s1", why="Backs the recall step.", **STUDY)
    assert out["proposed"] is True and "not been applied" in out["next"]
    assert repo.list_studies("index fund investing") == []              # nothing on the shelf yet
    assert [p["kind"] for p in proposals.pending(quality.today())] == ["study"]
    proposals.accept(out["proposal_id"], quality.today())
    shelf = repo.list_studies("index fund investing")
    assert len(shelf) == 1 and shelf[0]["url"] == STUDY["url"] and shelf[0]["retrieved_on"] == quality.today().isoformat()
    assert proposals.pending(quality.today()) == []


def test_a_study_needs_a_focus_a_real_link_and_is_not_duplicated(pg):
    with pytest.raises(writes.Refused, match="No learning focus"):
        writes.propose_study("c", **STUDY)
    set_focus()
    with pytest.raises(ValueError, match="web address"):
        writes.propose_study("c", **{**STUDY, "url": "javascript:alert(1)"})
    assert writes.propose_study("c", **STUDY)["proposed"] is True
    again = writes.propose_study("c", **STUDY)
    assert again["proposed"] is False and again["duplicate"] is True


def test_a_proposed_focus_cannot_replace_an_open_one(pg):
    set_focus()
    out = writes.propose_focus("c", "Spanish", "life", "Hold a 5 minute conversation.")
    item = proposals.pending(quality.today())[0]
    assert item["blocked"] and "Index fund investing" in item["blocked"]
    with pytest.raises(proposals.Conflict):
        proposals.accept(out["proposal_id"], quality.today())
    assert repo.active_focus()["topic"] == "Index fund investing"        # untouched
    assert proposals.get(out["proposal_id"])["status"] == "pending"


def test_an_accepted_focus_becomes_active(pg):
    out = writes.propose_focus("c", "Swimming", "sport", "Swim 400 m without stopping.", "it is Sat 07:00", "I swim")
    assert repo.active_focus() is None
    proposals.accept(out["proposal_id"], quality.today())
    focus = repo.active_focus()
    assert focus["topic"] == "Swimming" and focus["habit_tag"] == "learning" and focus["plan_then"] == "I swim"


def test_a_proposed_quest_names_the_week_and_what_it_would_replace(pg):
    this = quests.monday(quality.today())
    quests.save(this + timedelta(days=7), "training", 3, {})
    learning.ensure_habit()
    out = writes.propose_quest("c", "learning_sessions", 3, {"tag": "learning"}, "next")
    item = proposals.pending(quality.today())[0]
    assert item["payload"]["week_start"] == (this + timedelta(days=7)).isoformat()
    assert item["replaces"] == "3 training sessions"
    proposals.accept(out["proposal_id"], quality.today())
    assert repo.get_quest(this + timedelta(days=7))["kind"] == "learning_sessions"


def test_bad_quests_and_weeks_are_refused(pg):
    with pytest.raises(writes.Refused):
        writes.propose_quest("c", "sleep_hours", 3, {"hours": 4.0}, "next")
    with pytest.raises(writes.Refused, match="this' or 'next"):
        writes.propose_quest("c", "training", 3, {}, "last")
    assert proposals.pending(quality.today()) == []


def test_the_inbox_has_a_ceiling(pg):
    for i in range(proposals.MAX_PENDING):
        proposals.add("focus", {"topic": f"t{i}"})
    with pytest.raises(writes.Refused, match="inbox"):
        writes.propose_focus("c", "One more", "tech", "Do a thing.")


# ---------- the owner's side, through the web API ----------

@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    c = TestClient(app, headers=ORIGIN)
    if not pg.execute("SELECT 1 FROM auth.users WHERE username='david'").fetchone():
        service.create_user(pg, "david", "correct horse battery")
        pg.commit()
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


def test_inbox_routes_need_a_session(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    anon = TestClient(app, headers=ORIGIN)
    for method, path in (("get", "/api/proposals"), ("post", "/api/proposals/1/accept"),
                         ("get", "/api/connector/activity"), ("post", "/api/connector/activity/1/undo")):
        assert getattr(anon, method)(path).status_code == 401


def test_accept_and_reject_through_the_api(client):
    set_focus()
    keep = writes.propose_study("c", **STUDY)["proposal_id"]
    drop = writes.propose_study("c", **{**STUDY, "url": "https://example.org/other"})["proposal_id"]
    assert len(client.get("/api/proposals").json()["proposals"]) == 2
    assert client.post(f"/api/proposals/{keep}/accept").json()["applied"] == "study"
    assert client.post(f"/api/proposals/{drop}/reject").json() == {"rejected": True}
    assert client.post(f"/api/proposals/{drop}/accept").status_code == 404           # already decided
    assert client.post(f"/api/proposals/{keep}/reject").status_code == 404
    assert [s["url"] for s in client.get("/api/learning").json()["shelf"]] == [STUDY["url"]]


def test_accepting_a_blocked_focus_says_why(client):
    set_focus()
    pid = writes.propose_focus("c", "Spanish", "life", "Hold a short conversation.")["proposal_id"]
    r = client.post(f"/api/proposals/{pid}/accept")
    assert r.status_code == 409 and "already have a focus" in r.json()["detail"]


def test_activity_lists_writes_and_undo_removes_the_logged_session(client):
    out = writes.log_learning_session("claude", 45, None, "u1")
    rows = client.get("/api/connector/activity").json()["activity"]
    assert rows[0]["tool"] == "lifey_log_learning_session" and rows[0]["can_undo"] is True
    assert "45 minutes" in rows[0]["summary"]
    assert client.post(f"/api/connector/activity/{out['audit_id']}/undo").json() == {"undone": True}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM journal.activity_logs WHERE tag='learning'").fetchone()[0] == 0
    assert client.get("/api/connector/activity").json()["activity"][0]["can_undo"] is False
    assert client.post(f"/api/connector/activity/{out['audit_id']}/undo").status_code == 404


def test_undoing_a_pending_suggestion_rejects_it_and_a_decided_one_cannot_be_undone(client):
    set_focus()
    a = writes.propose_study("c", **STUDY)
    b = writes.propose_study("c", **{**STUDY, "url": "https://example.org/b"})
    assert client.post(f"/api/connector/activity/{a['audit_id']}/undo").status_code == 200
    assert proposals.get(a["proposal_id"])["status"] == "rejected"
    client.post(f"/api/proposals/{b['proposal_id']}/accept")
    assert client.post(f"/api/connector/activity/{b['audit_id']}/undo").status_code == 409
