"""Spotify OAuth for stdio MCP (@0xbarandiaran/spotify-mcp-server).

Writes tokens to ~/.spotify-mcp/config.json (what the MCP process reads).
Not MCP remote PKCE — Authorization Code against accounts.spotify.com.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from duckclaw.mcp_higgsfield_oauth import (
    _decode_oauth_state,
    _encode_oauth_state,
    resolve_oauth_redirect_uri,
)

SPOTIFY_PRESET_ID = "spotify"
SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = (
    "user-read-private user-read-email "
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "playlist-read-private playlist-modify-private playlist-modify-public "
    "user-library-read user-library-modify user-read-recently-played "
    "user-read-playback-position user-top-read"
)


def spotify_mcp_config_path() -> Path:
    override = (os.environ.get("SPOTIFY_MCP_CONFIG") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".spotify-mcp" / "config.json"


def spotify_mcp_config_authenticated() -> bool:
    path = spotify_mcp_config_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(str(data.get("accessToken") or data.get("access_token") or "").strip())


def _spotify_client_credentials() -> tuple[str, str]:
    client_id = (os.environ.get("SPOTIFY_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("SPOTIFY_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET son obligatorios en el host Gateway "
            "(Dashboard Spotify + redirect URI de DuckClaw OAuth callback)"
        )
    return client_id, client_secret


def persist_spotify_mcp_tokens(tokens: dict[str, str], *, pending: dict[str, Any] | None = None) -> Path:
    """Write MCP-compatible config.json; returns path written."""
    client_id, client_secret = _spotify_client_credentials()
    redirect_uri = str((pending or {}).get("redirect_uri") or resolve_oauth_redirect_uri()).strip()
    access = str(tokens.get("access_token") or "").strip()
    refresh = str(tokens.get("refresh_token") or "").strip()
    if not access:
        raise ValueError("Spotify token response missing access_token")
    expires_in = int(tokens.get("expires_in") or 3600)
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "redirectUri": redirect_uri,
        "accessToken": access,
        "refreshToken": refresh,
        "expiresAt": int(time.time() * 1000) + max(expires_in, 60) * 1000,
    }
    path = spotify_mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


async def start_spotify_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector
    from duckclaw.mcp_connector_presets import resolve_preset_id

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    preset_id = resolve_preset_id(str(connector.get("preset_id") or ""))
    if preset_id != SPOTIFY_PRESET_ID:
        raise ValueError("OAuth Spotify no está habilitado para esta plantilla MCP")

    client_id, _secret = _spotify_client_credentials()
    callback = resolve_oauth_redirect_uri(redirect_uri)
    state = _encode_oauth_state(
        {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email,
            "preset_id": SPOTIFY_PRESET_ID,
            "redirect_uri": callback,
            "client_id": client_id,
            "created_at": time.time(),
        }
    )
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        "show_dialog": "true",
    }
    query = httpx.QueryParams(params)
    return {
        "authorization_url": f"{SPOTIFY_AUTHORIZE_URL}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def exchange_spotify_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "").strip()
    if not redirect_uri:
        raise ValueError("OAuth pending missing redirect_uri")
    client_id, client_secret = _spotify_client_credentials()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 400:
            raise ValueError(f"Spotify token exchange failed: {resp.status_code} {resp.text[:300]}")
        tokens = resp.json()
    if not isinstance(tokens, dict) or not str(tokens.get("access_token") or "").strip():
        raise ValueError("Spotify token response invalid")
    # Normalize expires_in for persist
    out = {
        "access_token": str(tokens.get("access_token") or "").strip(),
        "refresh_token": str(tokens.get("refresh_token") or "").strip(),
        "expires_in": str(tokens.get("expires_in") or "3600"),
    }
    persist_spotify_mcp_tokens(out, pending=pending)
    return out


__all__ = [
    "SPOTIFY_PRESET_ID",
    "exchange_spotify_code_for_token",
    "persist_spotify_mcp_tokens",
    "spotify_mcp_config_authenticated",
    "spotify_mcp_config_path",
    "start_spotify_oauth",
    "_decode_oauth_state",
]
