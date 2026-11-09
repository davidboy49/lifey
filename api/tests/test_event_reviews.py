"""Event reviews: CRUD through the real auth and database, the day's data, loop-tag filters, photos, the
lessons view and the connector tools."""
import io
from datetime import timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import db
from app.auth import service
from app.connector import writes
from app.health import quality
from app.main import app
from test_connector import app_client, call, rpc  # noqa: F401
from test_connector_writes import audit_rows, raw_call, tokens

ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ATTACHMENTS_DIR", str(tmp_path / "files"))


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


def review(**over) -> dict:
    return {"date": ago(1), "event": "10 km race", "mood": 4, "energy": 3, "notes": "Hot start.",
            "went_well": "Even pacing", "would_change": "Earlier bed", "loop_tags": ["stress", "poor_sleep"],
            "lesson": "Sleep the night before matters", **over}


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


# ---------- auth ----------

def test_every_route_needs_a_session(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    c = TestClient(app, headers=ORIGIN)
    for method, path in [("get", "/api/event-reviews"), ("get", "/api/event-reviews/lessons"),
                         ("get", f"/api/event-reviews/day/{ago(1)}"), ("get", "/api/event-reviews/1"),
                         ("delete", "/api/event-reviews/1"), ("get", "/api/event-reviews/photos/1")]:
        assert getattr(c, method)(path).status_code == 401, path
    assert c.post("/api/event-reviews", json=review()).status_code == 401


def test_writes_from_another_site_are_refused(client):
    r = client.post("/api/event-reviews", json=review(), headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


# ---------- create, read, edit, delete ----------

def test_create_get_update_delete(client):
    r = client.post("/api/event-reviews", json=review())
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["event"] == "10 km race" and created["loop_tags"] == ["stress", "poor_sleep"]
    rid = created["id"]

    got = client.get(f"/api/event-reviews/{rid}").json()
    assert got["mood"] == 4 and got["lesson"] == "Sleep the night before matters" and got["photos"] == []

    up = client.put(f"/api/event-reviews/{rid}", json=review(mood=None, loop_tags=[], event="Night out"))
    assert up.status_code == 200
    assert up.json()["mood"] is None and up.json()["loop_tags"] == [] and up.json()["event"] == "Night out"

    assert client.delete(f"/api/event-reviews/{rid}").status_code == 204
    assert client.get(f"/api/event-reviews/{rid}").status_code == 404
    assert client.delete(f"/api/event-reviews/{rid}").status_code == 404


def test_only_event_and_date_are_required(client):
    r = client.post("/api/event-reviews", json={"date": ago(0), "event": "Quiet day"})
    assert r.status_code == 201
    body = r.json()
    assert body["mood"] is None and body["energy"] is None and body["loop_tags"] == [] and body["lesson"] == ""


@pytest.mark.parametrize("over,message", [
    ({"event": "  "}, "Name the event"),
    ({"event": "x" * 121}, "up to 120"),
    ({"date": "2999-01-01"}, "not happened yet"),
    ({"date": "yesterday"}, "Use a date"),
    ({"date": ago(401)}, "400 days"),
    ({"mood": 6}, "Mood must be 1 to 5"),
    ({"energy": 0}, "Energy must be 1 to 5"),
    ({"loop_tags": ["boredom"]}, "Unknown loop tag"),
    ({"lesson": "x" * 201}, "up to 200"),
    ({"notes": "x" * 2001}, "Nothing was saved"),
])
def test_bad_input_is_refused_and_nothing_is_saved(client, over, message):
    r = client.post("/api/event-reviews", json=review(**over))
    assert r.status_code == 422 and message in r.text
    assert client.get("/api/event-reviews").json()["reviews"] == []


def test_lesson_is_kept_to_one_line_and_tags_are_deduplicated(client):
    body = client.post("/api/event-reviews", json=review(lesson="Pace\nearly", loop_tags=["Poor sleep", "poor_sleep",
                                                                                          "urge"])).json()
    assert body["lesson"] == "Pace early" and body["loop_tags"] == ["urge", "poor_sleep"]


# ---------- list, filters, lessons ----------

def test_list_is_newest_first_and_filters_by_date_and_tag(client):
    for days, tags, event in [(10, ["drinking"], "Party"), (3, ["drinking", "stress"], "Work dinner"),
                              (1, [], "Race")]:
        client.post("/api/event-reviews", json=review(date=ago(days), loop_tags=tags, event=event))
    body = client.get("/api/event-reviews").json()
    assert [r["event"] for r in body["reviews"]] == ["Race", "Work dinner", "Party"]
    assert body["tag_counts"]["drinking"] == 2 and body["tag_counts"]["stress"] == 1
    assert body["tag_counts"]["loneliness"] == 0
    drinking = client.get("/api/event-reviews", params={"tag": "drinking"}).json()["reviews"]
    assert [r["event"] for r in drinking] == ["Work dinner", "Party"]
    recent = client.get("/api/event-reviews", params={"start": ago(5), "end": ago(2)}).json()["reviews"]
    assert [r["event"] for r in recent] == ["Work dinner"]
    assert client.get("/api/event-reviews", params={"tag": "nope"}).status_code == 422


def test_lessons_view_lists_only_reviews_with_a_lesson(client):
    client.post("/api/event-reviews", json=review(date=ago(5), lesson="Eat before"))
    client.post("/api/event-reviews", json=review(date=ago(2), lesson=""))
    client.post("/api/event-reviews", json=review(date=ago(1), lesson="Leave by 11"))
    lessons = client.get("/api/event-reviews/lessons").json()["lessons"]
    assert [(l["date"], l["lesson"]) for l in lessons] == [(ago(1), "Leave by 11"), (ago(5), "Eat before")]


# ---------- the day's data ----------

def test_day_data_shows_garmin_numbers_and_activities(client, pg):
    day = ago(1)
    pg.execute("""INSERT INTO health.daily_metrics (date, sleep_score, sleep_duration, hrv_last_night, resting_hr,
                                                    training_readiness, bb_max, bb_min)
                  VALUES (%s, 81, 27000, 52, 48, 70, 88, 20)""", (day,))
    pg.execute("""INSERT INTO health.activities (activity_id, date, started_local, name, type, duration_seconds,
                                                 distance_meters, avg_hr, raw)
                  VALUES (1, %s, %s, 'Morning run', 'running', 3000, 10000, 158, '{}')""", (day, f"{day} 06:30"))
    pg.commit()
    body = client.get(f"/api/event-reviews/day/{day}").json()
    assert body["has_data"] is True
    m = body["metrics"]
    assert (m["sleep_score"], m["sleep_seconds"], m["hrv_ms"], m["resting_hr"], m["training_readiness"],
            m["body_battery_high"]) == (81, 27000, 52, 48, 70, 88)
    [act] = body["activities"]
    assert act["type"] == "running" and act["distance_meters"] == 10000 and act["start"] == "06:30"
    assert act["avg_hr"] == 158


def test_a_day_without_data_says_so_and_missing_stays_null(client, pg):
    body = client.get(f"/api/event-reviews/day/{ago(2)}").json()
    assert body["has_data"] is False and body["activities"] == []
    assert all(v is None for v in body["metrics"].values())
    # A partial day: only resting HR recorded. The rest stays null, never zero.
    pg.execute("INSERT INTO health.daily_metrics (date, resting_hr) VALUES (%s, 50)", (ago(3),))
    pg.commit()
    part = client.get(f"/api/event-reviews/day/{ago(3)}").json()
    assert part["has_data"] is True and part["metrics"]["resting_hr"] == 50 and part["metrics"]["sleep_score"] is None


# ---------- photos ----------

def test_photos_upload_serve_and_delete_with_the_review(client, tmp_path):
    rid = client.post("/api/event-reviews", json=review()).json()["id"]
    r = client.post(f"/api/event-reviews/{rid}/photos",
                    files=[("files", ("medal.jpg", jpeg(), "image/jpeg")), ("files", ("two.jpg", jpeg(), "image/jpeg"))])
    assert r.status_code == 201, r.text
    photos = r.json()["photos"]
    assert len(photos) == 2 and photos[0]["has_thumb"]
    pid = photos[0]["id"]
    full = client.get(f"/api/event-reviews/photos/{pid}")
    assert full.status_code == 200 and full.headers["content-type"] == "image/jpeg"
    assert full.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/event-reviews/photos/{pid}/thumb").status_code == 200
    assert len(client.get(f"/api/event-reviews/{rid}").json()["photos"]) == 2

    assert client.delete(f"/api/event-reviews/photos/{pid}").status_code == 204
    assert client.get(f"/api/event-reviews/photos/{pid}").status_code == 404

    files = tmp_path / "files"
    assert any(p.is_file() for p in files.rglob("*"))
    assert client.delete(f"/api/event-reviews/{rid}").status_code == 204
    assert not any(p.is_file() for p in files.rglob("*"))      # files go with the review


def test_only_photos_are_accepted(client):
    rid = client.post("/api/event-reviews", json=review()).json()["id"]
    pdf = b"%PDF-1.4\n%%EOF\n"
    r = client.post(f"/api/event-reviews/{rid}/photos", files=[("files", ("x.pdf", pdf, "application/pdf"))])
    assert r.status_code == 422 and "Only photos" in r.text
    r = client.post(f"/api/event-reviews/{rid}/photos", files=[("files", ("x.jpg", b"not an image", "image/jpeg"))])
    assert r.status_code == 422
    assert client.post("/api/event-reviews/999/photos",
                       files=[("files", ("m.jpg", jpeg(), "image/jpeg"))]).status_code == 404


def test_existing_data_is_untouched_by_the_migration(pg):
    """The new tables stand alone; the only change to an old table is the wider audit ref_kind."""
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.execute("INSERT INTO journal.event_reviews (date, event, loop_tags) VALUES (CURRENT_DATE, 'x', "
                   "ARRAY['boredom'])")
    pg.rollback()


# ---------- connector ----------

def test_connector_read_tools_list_and_get(app_client, pg):
    tok = tokens(app_client, write=False)["access_token"]
    a = writes.create_review("c", "Party", ago(4), loop_tags=["drinking"], lesson="Leave by 11")
    writes.create_review("c", "Race", ago(1), mood=5, loop_tags=["stress"], notes="Felt strong")
    listed = call(app_client, tok, "lifey_list_reviews", {})
    assert [r["event"] for r in listed["reviews"]] == ["Race", "Party"]
    assert "notes" not in listed["reviews"][0]                     # the list is the summary only
    only = call(app_client, tok, "lifey_list_reviews", {"loop_tag": "drinking", "start": ago(7), "end": ago(0)})
    assert [r["event"] for r in only["reviews"]] == ["Party"] and only["loop_tag_counts"]["drinking"] == 1
    one = call(app_client, tok, "lifey_get_review", {"review_id": a["review_id"]})
    assert one["lesson"] == "Leave by 11" and one["day_data"]["has_data"] is False
    missing = raw_call(app_client, tok, "lifey_get_review", {"review_id": 999})
    assert missing["isError"]


def test_connector_create_needs_write_and_is_audited_idempotent_and_undoable(app_client, pg, monkeypatch):
    read_only = tokens(app_client, write=False)["access_token"]
    refused = raw_call(app_client, read_only, "lifey_create_review", {"event": "Race", "date": ago(1)})
    assert refused["isError"] and "read-only" in refused["content"][0]["text"]

    tok = tokens(app_client, write=True)["access_token"]
    args = {"event": "10 km race", "date": ago(1), "mood": 4, "loop_tags": ["stress"], "lesson": "Taper",
            "notes": "private words", "request_id": "rv-1"}
    first = call(app_client, tok, "lifey_create_review", args)
    again = call(app_client, tok, "lifey_create_review", args)
    assert first["created"] is True and again["created"] is False and again["duplicate"] is True
    assert audit_rows(pg) == [("lifey_create_review", "ok", "event_review")]
    with db.connect() as conn:
        stored_args = conn.execute("SELECT args FROM journal.connector_audit").fetchone()[0]
    assert "private words" not in str(stored_args)                   # free text stays in the review only

    bad = raw_call(app_client, tok, "lifey_create_review", {"event": "Race", "date": ago(1), "mood": 9})
    assert bad["isError"] and "1 to 5" in bad["content"][0]["text"]

    # Undo from Settings removes it.
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "owner2", "correct horse battery")
    web = TestClient(app, headers=ORIGIN)
    assert web.post("/api/auth/login", json={"username": "owner2", "password": "correct horse battery"}).status_code == 200
    [entry] = web.get("/api/connector/activity").json()["activity"]
    assert entry["can_undo"] is True
    assert web.post(f"/api/connector/activity/{entry['id']}/undo"
                    ).status_code == 200
    assert web.get(f"/api/event-reviews/{first['review_id']}").status_code == 404
