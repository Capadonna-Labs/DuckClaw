"""Tests for Notion MCP OAuth helpers."""

from __future__ import annotations

import pytest

from duckclaw.mcp_notion_oauth import resolve_notion_redirect_uri


def test_resolve_notion_redirect_uri_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_REDIRECT_URI", "https://example.test/api/v1/oauth/callback")
    assert resolve_notion_redirect_uri() == "https://example.test/api/v1/oauth/callback"


def test_resolve_notion_redirect_uri_from_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTION_REDIRECT_URI", raising=False)
    monkeypatch.setenv("DUCKCLAW_PUBLIC_URL", "https://gateway.test")
    assert resolve_notion_redirect_uri() == "https://gateway.test/api/v1/oauth/callback"
