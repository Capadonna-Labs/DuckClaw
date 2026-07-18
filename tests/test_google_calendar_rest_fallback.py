"""Self-check: Google Calendar REST fallback maps core tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from duckclaw.forge.skills.google_calendar_rest import (
    call_google_calendar_rest,
    uses_google_calendar_rest_fallback,
)


def test_uses_fallback_for_calendarmcp_preset() -> None:
    assert uses_google_calendar_rest_fallback(
        {"preset_id": "google_calendar", "endpoint_url": "https://calendarmcp.googleapis.com/mcp/v1"}
    )
    assert not uses_google_calendar_rest_fallback(
        {"preset_id": "notion", "endpoint_url": "https://mcp.notion.com/mcp"}
    )


def test_list_calendars_rest_success() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"items":[{"id":"primary","summary":"Me"}]}'
    resp.json.return_value = {"items": [{"id": "primary", "summary": "Me"}]}
    resp.text = resp.content.decode()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.forge.skills.google_calendar_rest.httpx.AsyncClient", return_value=client):
        out = asyncio.run(
            call_google_calendar_rest(
                "list_calendars",
                {},
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "primary" in out
    assert client.get.await_args.args[0].endswith("/users/me/calendarList")
