"""Tests for YouTube Analytics OAuth helpers (hardcoded endpoints, no PRM discovery)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

from duckclaw.mcp_youtube_oauth import (
    GOOGLE_AUTH_ENDPOINT,
    GOOGLE_TOKEN_ENDPOINT,
    exchange_youtube_code_for_token,
    start_youtube_oauth,
)
from duckclaw.mcp_higgsfield_oauth import _decode_oauth_state
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_handlers.mcp_connectors import _apply_upsert_mcp_connector


@pytest.fixture
def oauth_db(monkeypatch: pytest.MonkeyPatch):
    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "oauth.duckdb"))
    run_pending_migrations(con)
    monkeypatch.setenv("DUCKCLAW_MCP_OAUTH_STATE_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "yt-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "yt-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://test.local/oauth/callback")
    _apply_upsert_mcp_connector(
        con,
        {
            "tenant_id": "default",
            "actor_email": "admin@test.local",
            "preset_id": "google_youtube_analytics",
            "connector_id": "google_youtube_analytics",
            "enabled": True,
        },
    )
    yield con
    con.close()


def test_start_youtube_oauth_uses_hardcoded_endpoint_and_scopes(oauth_db) -> None:
    result = asyncio.run(
        start_youtube_oauth(
            oauth_db,
            connector_id="google_youtube_analytics",
            tenant_id="default",
            actor_email="admin@test.local",
        )
    )
    assert result["authorization_url"].startswith(f"{GOOGLE_AUTH_ENDPOINT}?")
    assert "yt-analytics.readonly" in result["authorization_url"]
    assert "youtube.readonly" in result["authorization_url"]
    assert "code_challenge=" in result["authorization_url"]
    assert "access_type=offline" in result["authorization_url"]
    decoded = _decode_oauth_state(result["state"])
    assert decoded["connector_id"] == "google_youtube_analytics"


def test_start_youtube_oauth_rejects_connector_without_pkce(oauth_db) -> None:
    _apply_upsert_mcp_connector(
        oauth_db,
        {
            "tenant_id": "default",
            "actor_email": "admin@test.local",
            "preset_id": "google_youtube_analytics",
            "connector_id": "no-pkce-connector",
            "enabled": True,
        },
    )
    with patch("duckclaw.mcp_connector_presets.preset_supports_oauth_pkce", return_value=False):
        with pytest.raises(ValueError):
            asyncio.run(
                start_youtube_oauth(
                    oauth_db,
                    connector_id="no-pkce-connector",
                    tenant_id="default",
                    actor_email="admin@test.local",
                )
            )


def test_start_youtube_oauth_missing_connector_raises(oauth_db) -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            start_youtube_oauth(
                oauth_db,
                connector_id="does-not-exist",
                tenant_id="default",
                actor_email="admin@test.local",
            )
        )


def test_exchange_youtube_code_for_token_hits_fixed_token_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "yt-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "yt-client-secret")

    class FakeResp:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"access_token": "yt-access-token", "refresh_token": "yt-refresh-token"}

    pending = {
        "redirect_uri": "http://test.local/oauth/callback",
        "code_verifier": "verifier-abc",
        "client_id": "yt-client-id",
    }

    called_endpoint: dict[str, str] = {}

    async def fake_post(self, url, data=None, headers=None):
        called_endpoint["url"] = url
        called_endpoint["client_secret"] = data.get("client_secret")
        return FakeResp()

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(exchange_youtube_code_for_token(code="auth-code", pending=pending))

    assert called_endpoint["url"] == GOOGLE_TOKEN_ENDPOINT
    assert called_endpoint["client_secret"] == "yt-client-secret"
    assert result == {"access_token": "yt-access-token", "refresh_token": "yt-refresh-token"}


def test_exchange_youtube_code_for_token_incomplete_pending_raises() -> None:
    with pytest.raises(ValueError):
        asyncio.run(exchange_youtube_code_for_token(code="auth-code", pending={}))
