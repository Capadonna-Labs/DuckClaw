"""Nexlev remote MCP: URL-only preset, discovered OAuth, grantable to any worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token
from duckclaw.mcp_connector_presets import preset_payload, preset_uses_mcp_dcr
from duckclaw.mcp_dcr_oauth import start_dcr_oauth


def test_nexlev_preset_matches_cursor_url() -> None:
    payload = preset_payload("nexlev")
    assert payload is not None
    assert payload["endpoint_url"] == "https://prod.dashboard.nexlev.io/api/mcp"
    assert payload["transport"] == "streamable_http"
    assert payload["auth_kind"] == "bearer"
    assert payload.get("launch_command") in (None, "")
    assert payload["metadata"]["oauth_pkce"] is True
    assert payload["metadata"]["oauth_provider"] == "mcp_dcr"
    assert preset_uses_mcp_dcr("nexlev") is True
    assert "prod.dashboard.nexlev.io" in payload["egress_hosts"]


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _Client:
    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.gets: list[str] = []

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def get(self, url: str) -> _Response:
        self.gets.append(url)
        if "oauth-protected-resource" in url:
            return _Response(
                {
                    "authorization_servers": ["https://auth.nexlev.test"],
                    "resource": "https://prod.dashboard.nexlev.io/api/mcp",
                }
            )
        return _Response(
            {
                "authorization_endpoint": "https://auth.nexlev.test/authorize",
                "registration_endpoint": "https://auth.nexlev.test/register",
            }
        )

    async def post(self, url: str, json: dict | None = None) -> _Response:
        del url, json
        return _Response({"client_id": "nexlev-client"})


def test_nexlev_oauth_start_discovers_prm_not_higgsfield() -> None:
    connector = {
        "preset_id": "nexlev",
        "endpoint_url": "https://prod.dashboard.nexlev.io/api/mcp",
    }
    client = _Client()

    async def _run() -> dict[str, str]:
        with patch("duckclaw.mcp_dcr_oauth.httpx.AsyncClient", return_value=client):
            with patch(
                "duckclaw.admin_mcp_connectors.get_mcp_connector",
                return_value=connector,
            ):
                with patch(
                    "duckclaw.admin_runtime_settings.resolve_runtime_setting",
                    return_value={"value": ""},
                ):
                    return await start_dcr_oauth(
                        MagicMock(),
                        connector_id="mcp_nexlev",
                        tenant_id="default",
                        actor_email="admin@example.com",
                    )

    out = asyncio.run(_run())
    assert out["authorization_url"].startswith("https://auth.nexlev.test/authorize?")
    assert "higgsfield" not in out["authorization_url"]
    assert "accounts.google.com" not in out["authorization_url"]
    assert any(
        url == "https://prod.dashboard.nexlev.io/.well-known/oauth-protected-resource/api/mcp"
        for url in client.gets
    )


def test_nexlev_bearer_refresh_does_not_use_google() -> None:
    db = MagicMock()
    db._read_only = True
    stale_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    connector = {
        "auth_kind": "bearer",
        "auth_secret_key": "mcp_nexlev.bearer",
        "tenant_id": "default",
        "owner_email": "admin@example.com",
        "connector_id": "mcp_nexlev",
        "preset_id": "nexlev",
    }

    def _resolve_setting(**kwargs: object) -> dict:
        key = kwargs.get("key")
        if key == "mcp_nexlev.bearer":
            return {"value": "stale-access"}
        if key == "mcp_nexlev.refresh":
            return {"value": "live-refresh"}
        if key == "mcp_nexlev.oauth_client_id":
            return {"value": "scoped-client", "value_json": {"redirect_uri": "http://127.0.0.1:3001/cb"}}
        return {"value": ""}

    with patch(
        "duckclaw.admin_mcp_connectors.resolve_runtime_setting",
        side_effect=lambda *a, **k: _resolve_setting(**k),
    ):
        with patch(
            "duckclaw.admin_mcp_connectors._fetchone",
            return_value={"value_text": "stale-access", "updated_at": stale_ts},
        ):
            with patch(
                "duckclaw.mcp_dcr_oauth.refresh_dcr_access_token",
                return_value={"access_token": "fresh-access", "refresh_token": "fresh-refresh"},
            ) as mock_refresh:
                with patch(
                    "duckclaw.mcp_google_workspace_oauth.refresh_google_access_token",
                    side_effect=AssertionError("google refresh"),
                ):
                    with patch("duckclaw.mcp_connector_oauth.persist_mcp_connector_oauth_tokens"):
                        assert resolve_connector_bearer_token(db, connector) == "fresh-access"

    assert mock_refresh.call_args.kwargs["endpoint_url"] == "https://prod.dashboard.nexlev.io/api/mcp"
    assert mock_refresh.call_args.kwargs["client_id"] == "scoped-client"
