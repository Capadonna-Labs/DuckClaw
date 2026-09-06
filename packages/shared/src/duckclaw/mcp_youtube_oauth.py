"""OAuth PKCE for YouTube Data/Analytics API (plain Google REST APIs, no hosted MCP/PRM).

Google's own hosted MCP servers (Gmail/Calendar/Workspace) publish RFC 9728 Protected
Resource Metadata that `mcp_google_workspace_oauth.py` discovers dynamically. YouTube Data
API v3 and YouTube Analytics API v2 have no such MCP surface — they're plain REST APIs — so
this module hardcodes Google's standard OAuth endpoints instead of discovering them, same
approach as `mcp_higgsfield_oauth.py` for a non-Google provider.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from duckclaw.mcp_google_workspace_oauth import (
    _google_client_credentials,
    _normalize_scopes,
    refresh_google_access_token,  # noqa: F401 — re-exported, reused as-is (scope-agnostic)
    resolve_google_redirect_uri,
)
from duckclaw.mcp_higgsfield_oauth import (
    _decode_oauth_state,
    _encode_oauth_state,
    _pkce_pair,
    build_oauth_completion_commands,  # noqa: F401 — re-exported for dispatcher symmetry
)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
YOUTUBE_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)


async def start_youtube_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector
    from duckclaw.mcp_connector_presets import preset_google_oauth_scopes, preset_supports_oauth_pkce

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    preset_id = str(connector.get("preset_id") or "")
    if not preset_supports_oauth_pkce(preset_id):
        raise ValueError("OAuth PKCE no está habilitado para esta plantilla MCP")

    callback = resolve_google_redirect_uri(redirect_uri)
    scopes = preset_google_oauth_scopes(preset_id) or list(YOUTUBE_OAUTH_SCOPES)
    scope_string = _normalize_scopes(scopes)

    client_id, _ = _google_client_credentials()
    verifier, challenge = _pkce_pair()
    state = _encode_oauth_state(
        {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email,
            "preset_id": preset_id,
            "code_verifier": verifier,
            "redirect_uri": callback,
            "client_id": client_id,
            "created_at": time.time(),
        }
    )
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback,
        "scope": scope_string,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    query = httpx.QueryParams(params)
    return {
        "authorization_url": f"{GOOGLE_AUTH_ENDPOINT}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def exchange_youtube_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    if not all([redirect_uri, code_verifier, client_id]):
        raise ValueError("OAuth pending payload incomplete")
    _, client_secret = _google_client_credentials()

    token_payload = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data=token_payload,
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 400:
            raise ValueError(f"token exchange failed: {resp.status_code} {resp.text[:300]}")
        tokens = resp.json()
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not access_token:
        raise ValueError("token response missing access_token")
    return {"access_token": access_token, "refresh_token": refresh_token}


__all__ = [
    "GOOGLE_AUTH_ENDPOINT",
    "GOOGLE_TOKEN_ENDPOINT",
    "YOUTUBE_OAUTH_SCOPES",
    "build_oauth_completion_commands",
    "exchange_youtube_code_for_token",
    "refresh_google_access_token",
    "start_youtube_oauth",
    "_decode_oauth_state",
]
