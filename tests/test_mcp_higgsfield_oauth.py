"""Tests for Higgsfield MCP OAuth helpers."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import duckdb
import pytest

from duckclaw.mcp_higgsfield_oauth import (
    _decode_oauth_state,
    _encode_oauth_state,
    _pkce_pair,
    complete_higgsfield_oauth,
    resolve_oauth_redirect_uri,
    start_higgsfield_oauth,
)
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_handlers.mcp_connectors import _apply_upsert_mcp_connector


@pytest.fixture
def oauth_db(monkeypatch: pytest.MonkeyPatch):
    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "oauth.duckdb"))
    run_pending_migrations(con)
    monkeypatch.setenv("DUCKCLAW_MCP_OAUTH_REDIRECT_URI", "http://test.local/oauth/callback")
    monkeypatch.setenv("DUCKCLAW_MCP_OAUTH_STATE_SECRET", "test-secret")
    _apply_upsert_mcp_connector(
        con,
        {
            "tenant_id": "default",
            "actor_email": "admin@test.local",
            "preset_id": "higgsfield",
            "connector_id": "mcp_higgsfield",
            "enabled": True,
        },
    )
    yield con
    con.close()


def test_pkce_challenge_is_s256() -> None:
    verifier, challenge = _pkce_pair()
    assert len(verifier) > 20
    assert challenge
    assert "=" not in challenge


def test_signed_state_roundtrip() -> None:
    import time

    os.environ["DUCKCLAW_MCP_OAUTH_STATE_SECRET"] = "test-secret"
    token = _encode_oauth_state({"connector_id": "mcp_higgsfield", "created_at": time.time()})
    decoded = _decode_oauth_state(token)
    assert decoded["connector_id"] == "mcp_higgsfield"


def test_resolve_oauth_redirect_uri_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_MCP_OAUTH_REDIRECT_URI", "https://admin.example/oauth/cb")
    assert resolve_oauth_redirect_uri() == "https://admin.example/oauth/cb"


def test_start_oauth_returns_authorization_url(oauth_db) -> None:
    meta = {
        "authorization_endpoint": "https://mcp.higgsfield.ai/oauth2/authorize",
        "registration_endpoint": "https://mcp.higgsfield.ai/oauth2/register",
        "token_endpoint": "https://mcp.higgsfield.ai/oauth2/token",
    }

    async def fake_register(*, redirect_uri: str, registration_endpoint: str) -> str:
        assert redirect_uri == "http://test.local/oauth/callback"
        return "duckclaw-client-id"

    with patch("duckclaw.mcp_higgsfield_oauth._fetch_oauth_metadata", new=AsyncMock(return_value=meta)):
        with patch("duckclaw.mcp_higgsfield_oauth._register_oauth_client", side_effect=fake_register):
            result = asyncio.run(
                start_higgsfield_oauth(
                    oauth_db,
                    connector_id="mcp_higgsfield",
                    tenant_id="default",
                    actor_email="admin@test.local",
                )
            )
    assert result["authorization_url"].startswith("https://mcp.higgsfield.ai/oauth2/authorize?")
    assert "code_challenge=" in result["authorization_url"]
    assert "state=" in result["authorization_url"]
    decoded = _decode_oauth_state(result["state"])
    assert decoded["connector_id"] == "mcp_higgsfield"


def test_complete_oauth_stores_bearer(oauth_db) -> None:
    meta = {
        "authorization_endpoint": "https://mcp.higgsfield.ai/oauth2/authorize",
        "registration_endpoint": "https://mcp.higgsfield.ai/oauth2/register",
        "token_endpoint": "https://mcp.higgsfield.ai/oauth2/token",
    }

    async def fake_register(*, redirect_uri: str, registration_endpoint: str) -> str:
        return "duckclaw-client-id"

    with patch("duckclaw.mcp_higgsfield_oauth._fetch_oauth_metadata", new=AsyncMock(return_value=meta)):
        with patch("duckclaw.mcp_higgsfield_oauth._register_oauth_client", side_effect=fake_register):
            started = asyncio.run(
                start_higgsfield_oauth(
                    oauth_db,
                    connector_id="mcp_higgsfield",
                    tenant_id="default",
                    actor_email="admin@test.local",
                )
            )

    state = started["state"]

    class FakeResp:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"access_token": "hf-access-token-xyz", "refresh_token": "hf-refresh"}

    with patch("duckclaw.mcp_higgsfield_oauth._fetch_oauth_metadata", new=AsyncMock(return_value=meta)):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=FakeResp())
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client
        mock_cm.__aexit__.return_value = None
        with patch("duckclaw.mcp_higgsfield_oauth.httpx.AsyncClient", return_value=mock_cm):
            result = asyncio.run(complete_higgsfield_oauth(oauth_db, code="auth-code-123", state=state))

    assert result["ok"] is True
    row = oauth_db.execute(
        "SELECT value_text FROM main.admin_runtime_settings "
        "WHERE domain = 'mcp_connector' AND key = 'mcp_higgsfield.bearer' AND secret = true"
    ).fetchone()
    assert row is not None
    assert row[0] == "hf-access-token-xyz"
