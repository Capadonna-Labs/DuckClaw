"""Tests for Notion MCP OAuth helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from duckclaw.mcp_notion_oauth import refresh_notion_access_token, resolve_notion_redirect_uri


def test_resolve_notion_redirect_uri_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_REDIRECT_URI", "https://example.test/api/v1/oauth/callback")
    assert resolve_notion_redirect_uri() == "https://example.test/api/v1/oauth/callback"


def test_resolve_notion_redirect_uri_matches_admin_mcp_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOTION_REDIRECT_URI", raising=False)
    monkeypatch.setenv(
        "DUCKCLAW_MCP_OAUTH_REDIRECT_URI",
        "https://prod.test/api/admin/mcp/connectors/oauth/callback",
    )
    assert (
        resolve_notion_redirect_uri()
        == "https://prod.test/api/admin/mcp/connectors/oauth/callback"
    )


def test_resolve_notion_redirect_uri_falls_back_to_google_oauth_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOTION_REDIRECT_URI", raising=False)
    monkeypatch.delenv("DUCKCLAW_MCP_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "https://prod.test/api/admin/mcp/connectors/oauth/callback",
    )
    assert (
        resolve_notion_redirect_uri()
        == "https://prod.test/api/admin/mcp/connectors/oauth/callback"
    )


def test_refresh_without_redirect_omits_redirect_uri_field() -> None:
    pr = MagicMock()
    pr.raise_for_status = MagicMock()
    pr.json.return_value = {"authorization_servers": ["https://auth.notion.test"]}
    meta = MagicMock()
    meta.raise_for_status = MagicMock()
    meta.json.return_value = {"token_endpoint": "https://auth.notion.test/token"}
    tok = MagicMock()
    tok.status_code = 200
    tok.content = b'{"access_token":"a"}'
    tok.json.return_value = {"access_token": "a"}

    with patch("httpx.get", side_effect=[pr, meta]):
        with patch("httpx.post", return_value=tok) as mock_post:
            with patch(
                "duckclaw.mcp_notion_oauth.resolve_notion_redirect_uri",
                return_value="https://WRONG/invented",
            ):
                refresh_notion_access_token("r", client_id="c")

    data = mock_post.call_args.kwargs["data"]
    assert "redirect_uri" not in data
