"""Journal attachments: what is accepted, what is stripped, who can fetch it, and the bot and backup-status paths."""
import asyncio
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import attachments, backup_status
from app.auth import service
from app.bot import bot
from app.bot import store
from app.health import quality
from app.main import app

ORIGIN = {"origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ATTACHMENTS_DIR", str(tmp_path / "files"))


def jpeg(size=(64, 48), exif=False) -> bytes:
    img = Image.new("RGB", size, (200, 80, 40))
    buf = io.BytesIO()
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCam"          # camera make
        data[0x0110] = "Model 9"
        img.save(buf, "JPEG", exif=data)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


# ---------- pure ----------

def test_type_comes_from_the_bytes_not_the_name():
    assert attachments.sniff(jpeg()) == "image/jpeg"
    assert attachments.sniff(PDF) == "application/pdf"
    assert attachments.sniff(b"MZ\x90\x00 this is an executable") is None
    assert attachments.sniff(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>") is None


def test_prepare_rejects_bad_empty_and_oversized_files():
    with pytest.raises(attachments.Rejected):
        attachments.prepare(b"", "a.jpg")
    with pytest.raises(attachments.Rejected):
        attachments.prepare(b"MZ" + b"\x00" * 100, "photo.jpg")                # an exe named .jpg
    with pytest.raises(attachments.Rejected):
        attachments.prepare(b"\xff\xd8\xff" + b"not really a jpeg", "x.jpg")   # right magic, unreadable
    with pytest.raises(attachments.Rejected):
        attachments.prepare(PDF + b"0" * attachments.MAX_BYTES, "big.pdf")


def test_photos_lose_their_metadata_and_get_a_thumbnail():
    out = attachments.prepare(jpeg(exif=True), "../../etc/passwd.jpg")
    kept = Image.open(io.BytesIO(out["data"]))
    assert 0x010F not in kept.getexif() and 0x0110 not in kept.getexif()
    assert out["filename"] == "passwd.jpg"                 # path parts and extension are cleaned
    assert out["thumb"] and Image.open(io.BytesIO(out["thumb"])).size[0] <= attachments.THUMB_EDGE


def test_large_photos_are_scaled_down():
    out = attachments.prepare(jpeg(size=(4000, 3000)), "big.jpg")
    assert max(out["width"], out["height"]) == attachments.MAX_EDGE


# ---------- API ----------

def upload(client, files, **data):
    return client.post("/api/attachments", files=files, data=data)


def test_new_entry_with_a_photo_and_a_pdf_round_trips(client):
    r = upload(client, [("files", ("lunch.jpg", jpeg(exif=True), "image/jpeg"))], note="Lunch, felt heavy")
    assert r.status_code == 201, r.text
    body = r.json()
    att = body["attachments"][0]
    assert att["mime"] == "image/jpeg" and att["has_thumb"]

    pdf = client.post(f"/api/attachments/{body['ids'][0]}", files=[("files", ("labs.pdf", PDF, "application/pdf"))])
    assert pdf.status_code == 201

    day = client.get("/api/journal", params={"days": 1}).json()
    entry = next(e for g in day["groups"] if not g["empty"] for e in g["entries"] if e["ids"] == body["ids"])
    assert [a["filename"] for a in entry["attachments"]] == ["lunch.jpg", "labs.pdf"]
    assert entry["note"] == "Lunch, felt heavy"

    thumb = client.get(f"/api/attachments/{att['id']}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert thumb.headers["x-content-type-options"] == "nosniff" and "sandbox" in thumb.headers["content-security-policy"]
    pdf_file = client.get(f"/api/attachments/{pdf.json()['attachments'][0]['id']}")
    assert pdf_file.headers["content-disposition"].startswith("attachment")     # PDFs download, never render inline
    served = Image.open(io.BytesIO(client.get(f"/api/attachments/{att['id']}").content))
    assert 0x010F not in served.getexif()


def test_a_rejected_file_leaves_no_entry_behind(client):
    before = client.get("/api/journal", params={"days": 1}).json()["count"]
    r = upload(client, [("files", ("virus.jpg", b"MZ" + b"\x00" * 200, "image/jpeg"))], note="x")
    assert r.status_code == 422
    assert client.get("/api/journal", params={"days": 1}).json()["count"] == before


def test_backdating_and_future_dates(client):
    past = (quality.today() - timedelta(days=3)).isoformat()
    ok = upload(client, [("files", ("a.jpg", jpeg(), "image/jpeg"))], date=past, time="09:30")
    assert ok.status_code == 201 and ok.json()["date"] == past and ok.json()["recalled"] is True
    future = (quality.today() + timedelta(days=1)).isoformat()
    assert upload(client, [("files", ("a.jpg", jpeg(), "image/jpeg"))], date=future).status_code == 422


def test_deleting_the_entry_removes_the_files(client, tmp_path):
    r = upload(client, [("files", ("a.jpg", jpeg(), "image/jpeg"))]).json()
    on_disk = [p for p in (tmp_path / "files").rglob("*") if p.is_file()]
    assert len(on_disk) == 2                                  # the photo and its thumbnail
    assert client.delete(f"/api/journal/{r['ids'][0]}").status_code == 204
    assert [p for p in (tmp_path / "files").rglob("*") if p.is_file()] == []
    assert client.get(f"/api/attachments/{r['attachments'][0]['id']}").status_code == 404


def test_limit_per_entry(client):
    first = upload(client, [("files", ("0.jpg", jpeg(), "image/jpeg"))]).json()
    for i in range(attachments.MAX_PER_ENTRY - 1):
        assert client.post(f"/api/attachments/{first['ids'][0]}",
                           files=[("files", (f"{i}.jpg", jpeg(), "image/jpeg"))]).status_code == 201
    over = client.post(f"/api/attachments/{first['ids'][0]}", files=[("files", ("x.jpg", jpeg(), "image/jpeg"))])
    assert over.status_code == 422 and "up to" in over.json()["detail"]


def test_everything_needs_a_session():
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/attachments", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))]).status_code == 401
    assert c.get("/api/attachments/1").status_code == 401
    assert c.get("/api/backups").status_code == 401


# ---------- the bot ----------

def test_a_photo_sent_to_the_bot_becomes_an_entry_with_the_caption(pg, monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    data = jpeg(exif=True)
    tg_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(data)))
    photo = SimpleNamespace(file_size=len(data), get_file=AsyncMock(return_value=tg_file))
    message = SimpleNamespace(photo=[photo], document=None, caption="Gym whiteboard",
                              reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message, callback_query=None)
    asyncio.run(bot.attachment_handler(update, SimpleNamespace()))
    logs = store.get_activity_logs(quality.today().isoformat())
    assert [l["note"] for l in logs] == ["Gym whiteboard"]
    found = attachments.for_logs([logs[0]["id"]])[logs[0]["id"]]
    assert found[0]["mime"] == "image/jpeg"
    assert "Saved to your journal" in message.reply_text.call_args.args[0]

    # moving it to yesterday from the button
    query = SimpleNamespace(edit_message_reply_markup=AsyncMock(), message=SimpleNamespace(reply_text=AsyncMock()))
    asyncio.run(bot.attachment_day(query, f"attday:{logs[0]['id']}:1"))
    moved = store.get_activity_log(logs[0]["id"])
    assert str(moved["date"]) == (quality.today() - timedelta(days=1)).isoformat()


def test_the_bot_refuses_a_file_that_is_not_a_photo_or_pdf(pg, monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    data = b"MZ" + b"\x00" * 300
    tg_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(data)))
    doc = SimpleNamespace(file_size=len(data), file_name="setup.exe", get_file=AsyncMock(return_value=tg_file))
    message = SimpleNamespace(photo=None, document=doc, caption=None, reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message, callback_query=None)
    asyncio.run(bot.attachment_handler(update, SimpleNamespace()))
    assert "Not saved" in message.reply_text.call_args.args[0]
    assert store.get_activity_logs(quality.today().isoformat()) == []


# ---------- backup status ----------

def run(pg, ago_h, ok, detail=None, bytes_=1000):
    pg.execute("INSERT INTO journal.backup_runs (started_at, finished_at, ok, bytes, files, destination, detail) "
               "VALUES (NOW() - make_interval(mins => (%s * 60)::int), NOW() - make_interval(mins => (%s * 60)::int), %s, %s, 3, 'lifeydrive:lifey', %s)",
               (ago_h, ago_h, ok, bytes_, detail))
    pg.commit()


def test_backup_state_never_ok_failed_auth_failed_and_stale(pg):
    assert backup_status.status()["state"] == "never"
    run(pg, 5, True)
    s = backup_status.status()
    assert s["state"] == "ok" and not s["needs_attention"] and s["last_ok_files"] == 3
    run(pg, 1, False, "Failed to create file system: couldn't login: invalid_grant: Token has been expired or revoked")
    s = backup_status.status()
    assert s["state"] == "failed" and s["needs_attention"] and "sign in again" in s["headline"]
    assert "rclone config reconnect" in s["hint"]
    run(pg, 0.5, False, "directory not found")
    s = backup_status.status()
    assert s["state"] == "failed" and "sign in" not in s["headline"] and s["hint"] == "directory not found"


def test_backup_goes_stale_when_nothing_succeeds_for_a_day_and_a_half(pg):
    run(pg, 40, True)
    s = backup_status.status()
    assert s["state"] == "stale" and s["needs_attention"]
