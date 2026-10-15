"""The page where the owner approves a connector, using Lifey's own sign-in.

The password is typed only here. The `request` id is random, single-use and
expires in ten minutes, so it also acts as the form's CSRF token.
"""
from __future__ import annotations

import asyncio
import html
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from ..auth import service
from . import oauth

router = APIRouter(prefix="/oauth", include_in_schema=False)

HEADERS = {"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
           "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                      "frame-ancestors 'none'; base-uri 'none'"}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Connect to Lifey</title><style>
:root{{color-scheme:light dark;--bg:#f6f4ef;--card:#fff;--ink:#1c1b19;--mut:#6b675f;--line:#dcd8cf;--acc:#2f6b57;--bad:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12110f;--card:#1b1a17;--ink:#f1eee7;--mut:#a39e92;--line:#34312b;--acc:#7fc4a8;--bad:#f2b8b5}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;background:var(--bg);
color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{width:100%;max-width:420px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}}
h1{{font-size:1.25rem;margin:0 0 4px}}p{{color:var(--mut);margin:.4rem 0}}ul{{margin:.6rem 0 1rem;padding-left:1.2rem}}
label{{display:block;margin:.9rem 0 .25rem;font-size:.9rem}}
input{{width:100%;padding:.7rem .8rem;border-radius:10px;border:1px solid var(--line);background:transparent;color:var(--ink);font:inherit}}
.row{{display:flex;gap:10px;margin-top:1.2rem}}
button{{flex:1;padding:.75rem;border-radius:10px;border:1px solid var(--line);font:inherit;font-weight:600;cursor:pointer;background:transparent;color:var(--ink)}}
button.go{{background:var(--acc);border-color:var(--acc);color:#fff}}
.err{{color:var(--bad);margin-top:.8rem}}
.opt{{display:flex;gap:10px;align-items:flex-start;margin:.2rem 0 .6rem;font-size:.9rem}}.opt input{{width:auto;margin-top:.25rem}}small{{color:var(--mut)}}
</style></head><body><main>
<h1>Connect {client} to Lifey</h1>
<p>Sign in to let it <strong>read</strong> your health, journal and habits.</p>
<ul><li>Daily metrics, sleep and activities</li><li>Journal entries and notes</li><li>Habit logs</li></ul>
<label class="opt"><input type="checkbox" name="write" value="1" form="f">
<span>Also let it <strong>log learning sessions</strong> and <strong>suggest</strong> studies, a monthly focus
and a weekly quest. Suggestions wait for your approval in Lifey; sessions can be undone. It still cannot
delete or edit anything else, or write your notes and reflections.</span></label>
<form id="f" method="post" action="/oauth/login" autocomplete="on">
<input type="hidden" name="request" value="{request}">
<label for="u">Username</label><input id="u" name="username" autocomplete="username" required autofocus>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
{error}
<div class="row"><button class="go" type="submit" name="action" value="allow">Allow</button>
<button type="submit" name="action" value="deny" formnovalidate>Deny</button></div>
</form>
<p><small>You will return to {host}. Revoke access any time with “sign out everywhere” in Lifey.</small></p>
</main></body></html>"""


def _page(request_id: str, client_name: str, redirect_uri: str, error: str = "", status: int = 200) -> HTMLResponse:
    host = urlparse(redirect_uri).hostname or "the app"
    body = PAGE.format(client=html.escape(client_name or "an app"), request=html.escape(request_id),
                       host=html.escape(host),
                       error=f'<p class="err" role="alert">{html.escape(error)}</p>' if error else "")
    return HTMLResponse(body, status_code=status, headers=HEADERS)


def _expired() -> HTMLResponse:
    return HTMLResponse("<!doctype html><meta charset=utf-8><title>Link expired</title>"
                        "<body style='font:16px system-ui;padding:2rem'>This connection link has expired or was "
                        "already used. Start again from Claude.</body>", status_code=400, headers=HEADERS)


@router.get("/login")
async def login_page(request: str = "") -> HTMLResponse:
    found = await asyncio.to_thread(oauth.load_request, request)
    if not found:
        return _expired()
    client, params = found
    return _page(request, client.client_name or "", str(params.redirect_uri))


@router.post("/login")
async def login_submit(req: Request, request: str = Form(""), username: str = Form(""),
                       password: str = Form(""), action: str = Form("allow"), write: str = Form("")):
    found = await asyncio.to_thread(oauth.load_request, request)
    if not found:
        return _expired()
    client, params = found
    redirect = str(params.redirect_uri)

    if action == "deny":
        await asyncio.to_thread(oauth.discard_request, request)
        return RedirectResponse(oauth.redirect_with(redirect, error="access_denied", state=params.state), 303,
                                headers=HEADERS)

    def check() -> tuple[int | None, int | None]:
        with db.connect() as conn:
            try:
                return service.authenticate(conn, username, password), None
            except service.Locked as locked:
                return None, locked.seconds

    user_id, locked_for = await asyncio.to_thread(check)
    if locked_for is not None:
        return _page(request, client.client_name or "", redirect,
                     "Too many attempts. Try again in a few minutes.", 429)
    if user_id is None:
        return _page(request, client.client_name or "", redirect, "Invalid username or password.", 401)

    granted = [oauth.SCOPE] + ([oauth.WRITE_SCOPE] if write == "1" else [])
    code = await asyncio.to_thread(oauth.issue_code, request, client.client_id, params, user_id, granted)
    return RedirectResponse(oauth.redirect_with(redirect, code=code, state=params.state), 303, headers=HEADERS)
