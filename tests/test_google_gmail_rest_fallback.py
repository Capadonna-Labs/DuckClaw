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


def test_gmail_rest_fallback_tool_specs_names() -> None:
    from duckclaw.forge.skills.google_gmail_rest import gmail_rest_fallback_tool_specs

    names = {getattr(s, "name", "") for s in gmail_rest_fallback_tool_specs()}
    assert "search_threads" in names
    assert "get_message" in names


def test_connect_worker_mcp_registers_gmail_rest_when_list_tools_fails() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from duckclaw.forge.skills import mcp_connector_bridge as bridge

    connector = {
        "connector_id": "mcp_google_gmail",
        "preset_id": "google_gmail",
        "endpoint_url": "https://gmailmcp.googleapis.com/mcp/v1",
        "transport": "streamable_http",
        "auth_kind": "bearer",
    }
    db = MagicMock()

    async def _boom(*_a, **_k):
        raise RuntimeError("list_tools down")

    with patch.object(bridge, "_list_connector_tools", _boom):
        with patch.object(bridge, "list_worker_mcp_connectors", return_value=[connector]):
            with patch.object(bridge, "resolve_connector_bearer_token", return_value="tok"):
                with patch.object(bridge, "_mcp_available", return_value=True):
                    tools = asyncio.run(
                        bridge.connect_worker_mcp_connectors(
                            db, worker_uid="uid", tenant_id="default"
                        )
                    )
    assert any(getattr(t, "name", "").endswith("__search_threads") for t in tools)


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


def test_get_message_rest_success() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b'{"id":"19f6fa44a4dec1eb"}'
    resp.json.return_value = {"id": "19f6fa44a4dec1eb"}
    resp.text = resp.content.decode()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.forge.skills.google_gmail_rest.httpx.AsyncClient", return_value=client):
        out = asyncio.run(
            call_google_gmail_rest(
                "get_message",
                {"messageId": "19f6fa44a4dec1eb"},
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "19f6fa44a4dec1eb" in out
    assert client.get.await_args.args[0].endswith("/users/me/messages/19f6fa44a4dec1eb")


def test_get_message_rejects_gmail_web_link() -> None:
    list_resp = MagicMock()
    list_resp.status_code = 200
    list_resp.content = b'{"messages":[{"id":"19f6fa44a4dec1eb","threadId":"19f6fa44a4dec1eb"}]}'
    list_resp.json.return_value = {
        "messages": [{"id": "19f6fa44a4dec1eb", "threadId": "19f6fa44a4dec1eb"}]
    }
    list_resp.text = list_resp.content.decode()

    meta_resp = MagicMock()
    meta_resp.status_code = 200
    meta_resp.content = b"{}"
    meta_resp.json.return_value = {
        "id": "19f6fa44a4dec1eb",
        "threadId": "19f6fa44a4dec1eb",
        "snippet": "See What's Shaping the Market",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "See what's moving the markets this week"},
                {"name": "From", "value": "Seeking Alpha <subscriptions@seekingalpha.com>"},
                {"name": "Date", "value": "Fri, 17 Jul 2026 05:34:00 -0500"},
            ]
        },
    }
    meta_resp.text = "{}"

    client = MagicMock()
    client.get = AsyncMock(side_effect=[list_resp, meta_resp])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.forge.skills.google_gmail_rest.httpx.AsyncClient", return_value=client):
        out = asyncio.run(
            call_google_gmail_rest(
                "get_message",
                {
                    "messageId": (
                        "https://mail.google.com/mail/u/0/#inbox/"
                        "FMfcgzQhVNfMDHmMskGmCMxCKRmRMGbZ"
                    )
                },
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "gmail_web_sync_id" in out
    assert "19f6fa44a4dec1eb" in out
    assert "Seeking Alpha" in out
    assert "Do NOT invent" in out
