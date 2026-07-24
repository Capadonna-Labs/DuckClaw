"""Spotify OAuth config helpers self-check."""

from __future__ import annotations

import json
from pathlib import Path

from duckclaw.mcp_spotify_oauth import (
    persist_spotify_mcp_tokens,
    spotify_mcp_config_authenticated,
)


def test_persist_spotify_mcp_tokens_writes_access(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    monkeypatch.setenv("SPOTIFY_MCP_CONFIG", str(cfg))
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    assert not spotify_mcp_config_authenticated()
    persist_spotify_mcp_tokens(
        {"access_token": "atok", "refresh_token": "rtok", "expires_in": "3600"},
        pending={"redirect_uri": "https://example.test/callback"},
    )
    assert spotify_mcp_config_authenticated()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["accessToken"] == "atok"
    assert data["clientId"] == "cid"
    assert data["redirectUri"] == "https://example.test/callback"
