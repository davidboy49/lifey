"""The remote MCP server Claude connects to (Streamable HTTP, OAuth, read-only tools)."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from . import oauth, tools

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

INSTRUCTIONS = (
    "Lifey is one person's private health and journal record (Garmin metrics, sleep, habits, journal notes). "
    "For 'summarise my week/month' start with lifey_digest. Use the other tools to go deeper. "
    "Missing values mean no data, never zero. Describe patterns as observations from one person's data, not "
    "causes, and do not diagnose; suggest a clinician for health worries. Dates are in the person's local time."
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
                enabled=True, valid_scopes=[oauth.SCOPE], default_scopes=[oauth.SCOPE]),
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

    return mcp.streamable_http_app()
