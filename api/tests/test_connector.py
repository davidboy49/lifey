"""The Claude connector: OAuth (register, authorize, token, refresh) and the read-only MCP tools."""
import base64
import hashlib
import json
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import service
from app.bot import store
from app.health import quality

CALLBACK = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def app_client(pg, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://lifey.test")
    monkeypatch.setenv("ENABLE_MCP", "1")
    from app.connector.login import router
    from app.connector.server import build

    inner = build()

    @asynccontextmanager
    async def lifespan(_):
        async with inner.router.lifespan_context(inner):
            yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.mount("/", inner)
    service.create_user(pg, "david", "correct horse battery")
    pg.commit()
    with TestClient(app, base_url="https://lifey.test", follow_redirects=False) as c:
        yield c


def register(c, redirect=CALLBACK):
    return c.post("/register", json={
        "redirect_uris": [redirect], "client_name": "Claude", "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "scope": "lifey:read"})


def authorize(c, client_id):
    r = c.get("/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK, "code_challenge": CHALLENGE,
        "code_challenge_method": "S256", "state": "xyz", "scope": "lifey:read", "resource": "https://lifey.test/mcp"})
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)["request"][0]


def get_tokens(c):
    client_id = register(c).json()["client_id"]
    request_id = authorize(c, client_id)
    done = c.post("/oauth/login", data={"request": request_id, "username": "david",
                                         "password": "correct horse battery", "action": "allow"})
    assert done.status_code == 303
    query = parse_qs(urlparse(done.headers["location"]).query)
    assert query["state"] == ["xyz"]
    tok = c.post("/token", data={"grant_type": "authorization_code", "code": query["code"][0],
                                 "redirect_uri": CALLBACK, "client_id": client_id, "code_verifier": VERIFIER})
    assert tok.status_code == 200, tok.text
    return client_id, query["code"][0], tok.json()


def rpc(c, token, method, params=None, id_=1):
    return c.post("/mcp", headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
                  content=json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}))


def call(c, token, name, arguments=None):
    r = rpc(c, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert not result.get("isError"), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def test_discovery_documents_exist(app_client):
    meta = app_client.get("/.well-known/oauth-authorization-server").json()
    assert meta["issuer"].startswith("https://lifey.test")
    assert "S256" in meta["code_challenge_methods_supported"]
    assert meta["registration_endpoint"].endswith("/register")
    assert app_client.get("/.well-known/oauth-protected-resource/mcp").status_code == 200


def test_registration_only_accepts_claude_or_loopback_callbacks(app_client):
    assert register(app_client).status_code == 201
    assert register(app_client, "http://localhost:6274/callback").status_code == 201
    assert register(app_client, "https://evil.example/cb").status_code == 400
    assert register(app_client, "http://evil.example/cb").status_code == 400


def test_mcp_needs_a_token(app_client):
    r = app_client.post("/mcp", headers=MCP_HEADERS,
                        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    assert r.status_code == 401 and "resource_metadata" in r.headers.get("www-authenticate", "")
    assert rpc(app_client, "not-a-real-token", "tools/list").status_code == 401


def test_wrong_password_is_refused_and_deny_returns_access_denied(app_client):
    client_id = register(app_client).json()["client_id"]
    page = app_client.get("/oauth/login", params={"request": authorize(app_client, client_id)})
    assert page.status_code == 200 and "Connect Claude to Lifey" in page.text
    request_id = authorize(app_client, client_id)
    bad = app_client.post("/oauth/login", data={"request": request_id, "username": "david", "password": "nope"})
    assert bad.status_code == 401 and "Invalid username or password" in bad.text
    deny = app_client.post("/oauth/login", data={"request": request_id, "action": "deny"})
    assert deny.status_code == 303 and "error=access_denied" in deny.headers["location"]
    again = app_client.get("/oauth/login", params={"request": request_id})
    assert again.status_code == 400                       # the request is single use
    assert app_client.get("/oauth/login", params={"request": "guess"}).status_code == 400


def test_full_flow_code_is_single_use_and_tools_work(app_client):
    store.log_activity(date_str=quality.today().isoformat(), category="unholy_habit", tag="alcohol",
                       note="two pints", value=2.0)
    client_id, code, tokens = get_tokens(app_client)
    assert tokens["token_type"].lower() == "bearer" and tokens["refresh_token"]

    replay = app_client.post("/token", data={"grant_type": "authorization_code", "code": code,
                                             "redirect_uri": CALLBACK, "client_id": client_id,
                                             "code_verifier": VERIFIER})
    assert replay.status_code == 400

    token = tokens["access_token"]
    assert rpc(app_client, token, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"}}).status_code == 200
    names = {t["name"] for t in rpc(app_client, token, "tools/list", id_=2).json()["result"]["tools"]}
    assert {"lifey_digest", "lifey_health", "lifey_journal", "lifey_habits", "lifey_sleep"} <= names

    habits = call(app_client, token, "lifey_habits", {"days": 7})
    assert habits["habits"][0]["tag"] == "alcohol" and habits["habits"][0]["total_units"] == 2.0
    journal = call(app_client, token, "lifey_journal", {"days": 7, "kind": "habit"})
    assert journal["entries"][0]["note"] == "two pints"
    digest = call(app_client, token, "lifey_digest", {"days": 7})
    assert digest["habits"][0]["habit"] == "Alcohol" and "reading_guide" in digest


def test_wrong_verifier_is_refused(app_client):
    client_id = register(app_client).json()["client_id"]
    done = app_client.post("/oauth/login", data={"request": authorize(app_client, client_id), "username": "david",
                                                 "password": "correct horse battery"})
    code = parse_qs(urlparse(done.headers["location"]).query)["code"][0]
    bad = app_client.post("/token", data={"grant_type": "authorization_code", "code": code,
                                          "redirect_uri": CALLBACK, "client_id": client_id,
                                          "code_verifier": "w" * 64})
    assert bad.status_code == 400


def test_refresh_rotates_and_sign_out_everywhere_revokes(app_client, pg):
    client_id, _, tokens = get_tokens(app_client)
    old_access = tokens["access_token"]
    r = app_client.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                        "client_id": client_id})
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert rpc(app_client, old_access, "tools/list").status_code == 401          # rotated away
    assert rpc(app_client, fresh["access_token"], "tools/list").status_code == 200
    again = app_client.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                            "client_id": client_id})
    assert again.status_code == 400                                              # old refresh token is dead

    uid = pg.execute("SELECT id FROM auth.users WHERE username='david'").fetchone()[0]
    service.revoke_all(pg, uid)
    assert rpc(app_client, fresh["access_token"], "tools/list").status_code == 401
