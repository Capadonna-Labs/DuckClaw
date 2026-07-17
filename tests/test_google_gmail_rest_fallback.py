"""Self-check: Google Gmail REST fallback maps core tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from duckclaw.forge.skills.google_gmail_rest import (
    call_google_gmail_rest,
    uses_google_gmail_rest_fallback,
)


def test_uses_fallback_for_gmailmcp_preset() -> None:
    assert uses_google_gmail_rest_fallback(
        {"preset_id": "google_gmail", "endpoint_url": "https://gmailmcp.googleapis.com/mcp/v1"}
    )
    assert not uses_google_gmail_rest_fallback(
        {"preset_id": "notion", "endpoint_url": "https://mcp.notion.com/mcp"}
    )


def test_search_threads_rest_success() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"threads":[{"id":"t1"}]}'
    resp.json.return_value = {"threads": [{"id": "t1"}]}
    resp.text = resp.content.decode()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.forge.skills.google_gmail_rest.httpx.AsyncClient", return_value=client):
        out = asyncio.run(
            call_google_gmail_rest(
                "search_threads",
                {"query": "is:inbox", "pageSize": 3},
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "t1" in out
    assert client.get.await_args.args[0].endswith("/users/me/threads")
    assert client.get.await_args.kwargs["params"]["q"] == "is:inbox"


def test_create_draft_posts_raw() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"id":"d1"}'
    resp.json.return_value = {"id": "d1"}
    resp.text = resp.content.decode()

    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.forge.skills.google_gmail_rest.httpx.AsyncClient", return_value=client):
        out = asyncio.run(
            call_google_gmail_rest(
                "create_draft",
                {"to": ["a@b.com"], "subject": "Hi", "body": "hola"},
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "d1" in out
    posted = client.post.await_args
    assert posted.args[0].endswith("/users/me/drafts")
    assert "raw" in posted.kwargs["json"]["message"]
