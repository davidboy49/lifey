"""The remote MCP server Claude connects to (Streamable HTTP, OAuth).

Read tools need "lifey:read". The few write tools need "lifey:write", which the owner grants on the consent
page; a read-only connection that calls one gets a plain refusal. See writes.py for what can be written."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from . import oauth, tools, writes

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Writes add a row or a suggestion. None of them edits or deletes, so none is destructive.
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def write_client() -> str | None:
    """The client id when this call carries the write scope, else a refusal the model can relay."""
    token = get_access_token()
    if token is None or oauth.WRITE_SCOPE not in token.scopes:
        raise ToolError("This connection is read-only. The owner can reconnect Lifey in Claude and tick the "
                        "capture option on the sign-in page to allow logging and suggestions.")
    return token.client_id

INSTRUCTIONS = (
    "Lifey is one person's private health and journal record (Garmin metrics, sleep, habits, journal notes). "
    "For 'summarise my week/month' start with lifey_digest. Use the other tools to go deeper. "
    "Missing values mean no data, never zero. Describe patterns as observations from one person's data, not "
    "causes, and do not diagnose; suggest a clinician for health worries. Dates are in the person's local time. "
    "Writes are limited: lifey_log_learning_session records minutes the person says they studied (use a request_id "
    "so a retry is not logged twice), and the lifey_propose_* tools put a suggestion in an inbox that the person "
    "accepts or rejects in Lifey. Nothing proposed has taken effect. Never invent a study: only propose one you "
    "found, with a working link, and say what it is and is not evidence for. You cannot close a focus, write the "
    "person's reflection or recall, or edit or delete anything."
)


def build():
    """Return the Starlette app serving /mcp plus the OAuth endpoints, ready to mount at '/'."""
    base = oauth.public_url()
    host = urlparse(base).netloc
    mcp = FastMCP(
        "Lifey",
        instructions=INSTRUCTIONS,
        auth_server_provider=oauth.LifeyProvider(),
        auth=AuthSettings(
            issuer_url=base,
            resource_server_url=f"{base}/mcp",
            required_scopes=[oauth.SCOPE],
            validate_token_resource=False,   # one resource server; tokens are ours
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[oauth.SCOPE, oauth.WRITE_SCOPE], default_scopes=[oauth.SCOPE]),
            revocation_options=RevocationOptions(enabled=True),
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host, "localhost:*", "127.0.0.1:*"],
            allowed_origins=[base, "https://claude.ai", "https://claude.com", "http://localhost:*",
                             "http://127.0.0.1:*"]),
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_digest(days: int = 14) -> dict:
        """One compact picture of the last N days (default 14, max 365): health metric summaries against the
        previous period, sleep debt and regularity, habit counts, and the journal notes. Start here for any
        'summarise my week' request."""
        return await asyncio.to_thread(tools.digest, days)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_health(days: int = 14) -> dict:
        """Daily Garmin metrics for the last N days: per-metric mean/min/max/latest and change versus the previous
        equal period, plus the daily rows (sleep, HRV, resting HR, readiness, steps, stress, SpO2)."""
        return await asyncio.to_thread(tools.health, days)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_sleep() -> dict:
        """Sleep analysis: debt over the last 14 recorded nights, 28-day progress to target, bed/wake regularity,
        weekend vs weekday, outcomes after short vs adequate nights, and evidence-based suggestions."""
        return await asyncio.to_thread(tools.sleep)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_journal(days: int = 14, kind: str | None = None) -> dict:
        """Journal entries for the last N days, newest first. `kind` can be note, habit, checkin, quit or
        training. A day with no entries is unknown, not a clean day."""
        return await asyncio.to_thread(tools.journal, days, kind)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_habits(days: int = 30) -> dict:
        """Habit logs for the last N days (default 30): per habit the entries, total units, days logged, last
        logged and recent notes."""
        return await asyncio.to_thread(tools.habits, days)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_checkins(days: int = 30) -> dict:
        """Evening check-in answers for the last N days (alcohol, caffeine after 2pm, late meal, workout effort).
        Unanswered days are unknown, not zero."""
        return await asyncio.to_thread(tools.checkins, days)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_activities(days: int = 30) -> dict:
        """Workouts and activities from Garmin for the last N days (default 30)."""
        return await asyncio.to_thread(tools.activities, days)

    @mcp.tool(annotations=READ_ONLY)
    async def lifey_learning() -> dict:
        """The one thing being learned this month: topic, category, the outcome to reach, sessions so far and
        the studies already kept. Use it to look for research on how to learn that topic better. Only the topic
        and outcome are shared, never journal notes."""
        return await asyncio.to_thread(tools.learning)

    @mcp.tool(annotations=WRITES)
    async def lifey_log_learning_session(minutes: float, date: str | None = None,
                                         request_id: str | None = None) -> dict:
        """Record a learning session the person says they did: minutes (1 to 600) on `date` (YYYY-MM-DD, today if
        omitted, at most 7 days back). It is added to their "Learning" habit and can be undone in Lifey. Pass a
        stable `request_id` for this session so a retry does not log it twice. Needs the write permission."""
        client = write_client()
        try:
            return await asyncio.to_thread(writes.log_learning_session, client, minutes, date, request_id)
        except writes.Refused as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=WRITES)
    async def lifey_propose_study(citation: str, url: str, finding: str, why: str = "",
                                  request_id: str | None = None) -> dict:
        """Suggest a study for the person's current learning topic. `citation`: authors, year, title. `url`: a
        working http(s) link you actually opened. `finding`: what it found, in one sentence, as the source says
        it. `why`: one line on why it helps this topic. It goes to an inbox; the person decides. Needs the write
        permission."""
        client = write_client()
        try:
            return await asyncio.to_thread(writes.propose_study, client, citation, url, finding, why, request_id)
        except (writes.Refused, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=WRITES)
    async def lifey_propose_focus(topic: str, category: str, outcome: str, plan_if: str = "", plan_then: str = "",
                                  why: str = "", request_id: str | None = None) -> dict:
        """Suggest the next monthly learning focus. `category`: tech, life, sport, money, investing or other.
        `outcome`: something the person can check themselves by month end. It goes to an inbox and is only used
        if the person accepts it and has no focus open. Needs the write permission."""
        client = write_client()
        try:
            return await asyncio.to_thread(writes.propose_focus, client, topic, category, outcome, plan_if,
                                           plan_then, why, request_id)
        except writes.Refused as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=WRITES)
    async def lifey_propose_quest(kind: str, target: int, params: dict | None = None, week: str = "next",
                                  request_id: str | None = None) -> dict:
        """Suggest a weekly quest for `week` ('this' or 'next'). `kind`: habit_free (params.tag), sleep_hours
        (params.hours 6.5, 7, 7.5 or 8), bed_before (params.time like 23:00), training, or learning_sessions
        (params.tag, usually 'learning'). `target` is 1 to 7. It goes to an inbox for the person to accept. Needs
        the write permission."""
        client = write_client()
        try:
            return await asyncio.to_thread(writes.propose_quest, client, kind, target, params, week, request_id)
        except writes.Refused as exc:
            raise ToolError(str(exc)) from exc

    return mcp.streamable_http_app()
