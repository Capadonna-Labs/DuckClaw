"""Tests for Google Workspace MCP OAuth helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from duckclaw.mcp_google_workspace_oauth import (
    discover_google_mcp_oauth,
    exchange_google_code_for_token,
    protected_resource_metadata_url,
    resolve_google_oauth_scopes,
    resolve_google_redirect_uri,
    start_google_workspace_oauth,
)


def test_protected_resource_metadata_url_workspace() -> None:
    url = protected_resource_metadata_url("https://workspacemcp.googleapis.com/mcp/v1")
    assert url == "https://workspacemcp.googleapis.com/.well-known/oauth-protected-resource/mcp/v1"


def test_resolve_google_redirect_uri_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://admin.test/api/v1/oauth/callback")
    assert resolve_google_redirect_uri() == "https://admin.test/api/v1/oauth/callback"


def test_resolve_google_redirect_uri_env_wins_over_admin_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://host.test/api/v1/oauth/callback")
    explicit = "https://host.test:8443/api/admin/mcp/connectors/oauth/callback"
    assert resolve_google_redirect_uri(explicit) == "https://host.test/api/v1/oauth/callback"


def test_resolve_google_oauth_scopes_filters_write_scopes() -> None:
    prm = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]
    scopes = resolve_google_oauth_scopes(prm, read_only=True)
    assert "gmail.modify" not in scopes
    assert "mail.google.com" not in scopes
    assert "gmail.readonly" in scopes
    assert "calendar.readonly" in scopes


def test_resolve_google_oauth_scopes_keeps_maps_when_no_readonly_variant() -> None:
    prm = ["https://www.googleapis.com/auth/maps-platform.mapstools"]
    scopes = resolve_google_oauth_scopes(prm, read_only=True)
    assert "maps-platform.mapstools" in scopes


def test_discover_google_mcp_oauth_parses_prm_and_oidc() -> None:
    prm = {
        "authorization_servers": ["https://accounts.google.com/"],
        "resource": "https://gmailmcp.googleapis.com/mcp/v1",
        "scopes_supported": [
            "https://www.googleapis.com/auth/gmail.readonly",
            "openid",
        ],
    }
    oidc = {
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
    }

    async def fake_get(url: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "oauth-protected-resource" in url:
            resp.json.return_value = prm
        else:
            resp.json.return_value = oidc
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("duckclaw.mcp_google_workspace_oauth.httpx.AsyncClient", return_value=client):
        meta, pr_data, resource, scopes = asyncio.run(
            discover_google_mcp_oauth("https://gmailmcp.googleapis.com/mcp/v1")
        )

    assert meta["token_endpoint"] == "https://oauth2.googleapis.com/token"
    assert pr_data["resource"] == "https://gmailmcp.googleapis.com/mcp/v1"
    assert resource == "https://gmailmcp.googleapis.com/mcp/v1"
    assert "gmail.readonly" in scopes


def test_start_google_workspace_oauth_authorize_url_includes_workspace_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")

    connector = {
        "preset_id": "google_workspace",
        "endpoint_url": "https://workspacemcp.googleapis.com/mcp/v1",
        "read_only": True,
    }

    async def fake_discover(_endpoint: str, *, read_only: bool = True) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        del read_only
        return (
            {"authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth"},
            {"scopes_supported": ["https://www.googleapis.com/auth/gmail.readonly"]},
            "https://workspacemcp.googleapis.com/mcp/v1",
            "openid https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly",
        )

    with (
        patch(
            "duckclaw.admin_mcp_connectors.get_mcp_connector",
            return_value=connector,
        ),
        patch(
            "duckclaw.mcp_google_workspace_oauth.discover_google_mcp_oauth",
            new=fake_discover,
        ),
        patch(
            "duckclaw.mcp_google_workspace_oauth.resolve_google_redirect_uri",
            return_value="https://admin.test/callback",
        ),
    ):
        result = asyncio.run(
            start_google_workspace_oauth(
                None,
                connector_id="mcp_google_workspace",
                tenant_id="tenant-1",
                actor_email="user@example.com",
            )
        )

    assert "accounts.google.com" in result["authorization_url"]
    assert "gmail.readonly" in result["authorization_url"]
    assert "code_challenge=" in result["authorization_url"]


def test_start_google_calendar_oauth_uses_preset_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")

    connector = {
        "preset_id": "google_calendar",
        "endpoint_url": "https://calendarmcp.googleapis.com/mcp/v1",
        "read_only": False,
    }

    async def fake_discover(_endpoint: str, *, read_only: bool = True) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        del read_only
        return (
            {"authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth"},
            {"scopes_supported": ["https://www.googleapis.com/auth/calendar.readonly"]},
            "https://calendarmcp.googleapis.com/mcp/v1",
            "openid https://www.googleapis.com/auth/calendar.readonly",
        )

    with (
        patch("duckclaw.admin_mcp_connectors.get_mcp_connector", return_value=connector),
        patch("duckclaw.mcp_google_workspace_oauth.discover_google_mcp_oauth", new=fake_discover),
        patch(
            "duckclaw.mcp_google_workspace_oauth.resolve_google_redirect_uri",
            return_value="https://admin.test/callback",
        ),
    ):
        result = asyncio.run(
            start_google_workspace_oauth(
                None,
                connector_id="mcp_google_calendar",
                tenant_id="tenant-1",
                actor_email="user@example.com",
            )
        )

    assert "calendar.events" in result["authorization_url"]
    assert "calendar.calendarlist.readonly" in result["authorization_url"]
    assert "calendar.events.readonly" in result["authorization_url"]
    assert "calendar.events.freebusy" in result["authorization_url"]


def test_exchange_google_code_for_token_sends_client_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "top-secret")

    captured: dict[str, Any] = {}

    async def fake_post(url: str, data: dict[str, str] | None = None, headers: dict[str, str] | None = None):
        del url, headers
        captured.update(data or {})
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"access_token": "at-123", "refresh_token": "rt-456"}
        return resp

    client = MagicMock()
    client.post = AsyncMock(side_effect=fake_post)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    pending = {
        "redirect_uri": "https://admin.test/callback",
        "code_verifier": "verifier",
        "client_id": "cid.apps.googleusercontent.com",
        "endpoint_url": "https://calendarmcp.googleapis.com/mcp/v1",
        "resource": "https://calendarmcp.googleapis.com/mcp/v1",
    }

    with (
        patch(
            "duckclaw.mcp_google_workspace_oauth.discover_google_mcp_oauth",
            new=AsyncMock(
                return_value=(
                    {"token_endpoint": "https://oauth2.googleapis.com/token"},
                    {},
                    "https://gmailmcp.googleapis.com/mcp/v1",
                    "openid",
                )
            ),
        ),
        patch("duckclaw.mcp_google_workspace_oauth.httpx.AsyncClient", return_value=client),
    ):
        tokens = asyncio.run(exchange_google_code_for_token(code="auth-code", pending=pending))

    assert tokens["access_token"] == "at-123"
    assert captured["client_secret"] == "top-secret"
    assert captured["code_verifier"] == "verifier"
    assert captured["resource"] == "https://calendarmcp.googleapis.com/mcp/v1"
