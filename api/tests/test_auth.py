import pytest
from fastapi.testclient import TestClient

from app.auth import cli, security, service
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}
PASSWORD = "correct horse battery"


@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")  # TestClient speaks http
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    return TestClient(app)


@pytest.fixture
def user(pg):
    return service.create_user(pg, "David", PASSWORD)


def login(client, username="david", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password}, headers=ORIGIN)


def test_everything_requires_a_session_except_login_logout_and_healthz(client):
    public = {("POST", "/api/auth/login"), ("POST", "/api/auth/logout")}
    # The OpenAPI schema lists every route, including nested routers.
    schema = app.openapi()["paths"]
    checked = []
    for path, methods in schema.items():
        if not path.startswith("/api/"):
            continue
        for method in methods:
            if (method.upper(), path) in public:
                continue
            resp = client.request(method.upper(), path, headers=ORIGIN)
            assert resp.status_code == 401, f"{method.upper()} {path} answered {resp.status_code} without a session"
            checked.append(path)
    assert {"/api/today", "/api/auth/me", "/api/auth/password", "/api/money/import"} <= set(checked)
    assert client.get("/healthz").status_code == 200


def test_login_sets_a_hardened_cookie_and_unlocks_the_api(client, user):
    resp = login(client)
    assert resp.status_code == 200 and resp.json() == {"username": "david"}
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert client.get("/api/auth/me").json() == {"username": "david"}
    assert client.get("/api/today").status_code == 200


def test_username_is_case_insensitive(client, user):
    assert login(client, username="  DAVID ").status_code == 200


def test_wrong_password_and_unknown_user_look_identical(client, user):
    wrong = login(client, password="not the password")
    unknown = login(client, username="nobody", password="whatever whatever")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "set-cookie" not in wrong.headers


def test_logout_ends_the_session_server_side(client, user):
    token = login(client).cookies["lifey_session"]
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 204
    replay = TestClient(app, cookies={"lifey_session": token})
    assert replay.get("/api/auth/me").status_code == 401


def test_lockout_after_repeated_failures_even_for_the_right_password(client, user):
    for _ in range(service.MAX_FAILURES):
        assert login(client, password="wrong wrong wrong").status_code == 401
    locked = login(client)  # correct password, but throttled
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_failures_reset_after_a_successful_login(client, user):
    for _ in range(service.MAX_FAILURES - 1):
        login(client, password="wrong wrong wrong")
    assert login(client).status_code == 200
    for _ in range(service.MAX_FAILURES - 1):
        assert login(client, password="wrong wrong wrong").status_code == 401


def test_only_hashes_are_stored(client, user, pg):
    token = login(client).cookies["lifey_session"]
    stored_hash = pg.execute("SELECT password_hash FROM auth.users").fetchone()[0]
    assert stored_hash.startswith("$argon2id$") and PASSWORD not in stored_hash
    raw = bytes(pg.execute("SELECT token_hash FROM auth.sessions").fetchone()[0])
    assert raw == security.token_hash(token) and token.encode() not in raw


def test_expired_sessions_are_rejected(client, user, pg):
    login(client)
    pg.execute("UPDATE auth.sessions SET expires_at = NOW() - interval '1 minute'")
    pg.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_absolute_lifetime_cannot_be_extended_by_activity(client, user, pg):
    login(client)
    pg.execute("UPDATE auth.sessions SET absolute_expires_at = NOW() - interval '1 second'")
    pg.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_state_changing_requests_need_a_known_origin(client, user):
    body = {"username": "david", "password": PASSWORD}
    assert client.post("/api/auth/login", json=body).status_code == 403
    assert client.post("/api/auth/login", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/login", json=body, headers=ORIGIN).status_code == 200


def test_changing_password_ends_other_sessions_and_enforces_length(client, user):
    phone = TestClient(app, cookies={"lifey_session": login(client).cookies["lifey_session"]})
    login(client)  # a second session, held by `client`
    assert client.post("/api/auth/password", json={"current": "nope nope nope", "new": "another long password"},
                       headers=ORIGIN).status_code == 401
    assert client.post("/api/auth/password", json={"current": PASSWORD, "new": "short"},
                       headers=ORIGIN).status_code == 422
    ok = client.post("/api/auth/password", json={"current": PASSWORD, "new": "another long password"}, headers=ORIGIN)
    assert ok.status_code == 200 and ok.json()["other_sessions_ended"] == 1
    assert phone.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200
    assert login(TestClient(app), password="another long password").status_code == 200


def test_disabled_user_cannot_log_in_and_loses_sessions(client, user, pg):
    login(client)
    pg.execute("UPDATE auth.users SET disabled = TRUE")
    pg.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(TestClient(app)).status_code == 401


def test_weak_passwords_cannot_create_an_account(pg):
    with pytest.raises(ValueError):
        service.create_user(pg, "someone", "short")


def test_cli_creates_users_with_a_hidden_prompt(pg, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", pg.info.dsn) if False else None
    answers = iter(["a long enough password", "a long enough password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-user", "Priya"]) == 0
    assert cli.main(["list"]) == 0
    assert "priya" in capsys.readouterr().out
