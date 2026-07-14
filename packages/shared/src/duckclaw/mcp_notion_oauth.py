"""OAuth PKCE for Notion hosted MCP (mcp.notion.com) via dynamic client registration."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from duckclaw.mcp_higgsfield_oauth import (
    OAUTH_CLIENT_DOMAIN,
    _decode_oauth_state,
    _encode_oauth_state,
    _pkce_pair,
    build_oauth_completion_commands,
)

NOTION_MCP_RESOURCE = "https://mcp.notion.com/mcp"
NOTION_PROTECTED_RESOURCE_URL = "https://mcp.notion.com/.well-known/oauth-protected-resource/mcp"
NOTION_PRESET_ID = "notion"


def resolve_notion_redirect_uri(explicit: str | None = None) -> str:
    override = (explicit or os.environ.get("NOTION_REDIRECT_URI") or "").strip()
    if override:
        return override.rstrip("/")
    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return f"{public}/api/v1/oauth/callback"
    admin = (os.environ.get("DUCKCLAW_ADMIN_URL") or "").strip().rstrip("/")
    if admin:
        from urllib.parse import urlparse

        parsed = urlparse(admin)
        if parsed.scheme and parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}/api/v1/oauth/callback"
    from duckclaw.mcp_higgsfield_oauth import resolve_oauth_redirect_uri

    return resolve_oauth_redirect_uri(explicit)


async def discover_notion_oauth_metadata() -> tuple[dict[str, Any], str]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        pr_resp = await client.get(NOTION_PROTECTED_RESOURCE_URL)
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()
        if not isinstance(pr_data, dict):
            raise ValueError("invalid notion protected resource metadata")
        auth_servers = pr_data.get("authorization_servers")
        if not isinstance(auth_servers, list) or not auth_servers:
            raise ValueError("notion protected resource missing authorization_servers")
        auth_base = str(auth_servers[0]).rstrip("/")
        meta_resp = await client.get(f"{auth_base}/.well-known/oauth-authorization-server")
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        if not isinstance(meta, dict):
            raise ValueError("invalid notion authorization server metadata")
        resource = str(pr_data.get("resource") or NOTION_MCP_RESOURCE).strip()
        return meta, resource


def _load_notion_client_id(db: Any, *, tenant_id: str, redirect_uri: str) -> str:
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    row = resolve_runtime_setting(
        db,
        tenant_id=tenant_id,
        actor_email="",
        domain=OAUTH_CLIENT_DOMAIN,
        key=f"{NOTION_PRESET_ID}.client_id",
    )
    client_id = str(row.get("value_text") or row.get("value") or "").strip()
    meta = row.get("value_json")
    stored_redirect = ""
    if isinstance(meta, dict):
        stored_redirect = str(meta.get("redirect_uri") or "").strip()
    if client_id and stored_redirect == redirect_uri:
        return client_id
    return ""


async def _register_notion_oauth_client(*, redirect_uri: str, registration_endpoint: str) -> str:
    payload = {
        "client_name": "DuckClaw Admin",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(registration_endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
    client_id = str(data.get("client_id") or "").strip()
    if not client_id:
        raise ValueError("notion oauth registration missing client_id")
    return client_id


async def _resolve_notion_client_id(
    db: Any | None,
    *,
    tenant_id: str,
    redirect_uri: str,
) -> str:
    if db is not None:
        cached = _load_notion_client_id(db, tenant_id=tenant_id, redirect_uri=redirect_uri)
        if cached:
            return cached
    meta, _ = await discover_notion_oauth_metadata()
    registration_endpoint = str(meta.get("registration_endpoint") or "").strip()
    if not registration_endpoint:
        raise ValueError("Notion OAuth metadata missing registration_endpoint")
    client_id = await _register_notion_oauth_client(
        redirect_uri=redirect_uri,
        registration_endpoint=registration_endpoint,
    )
    # ponytail: client_id va en OAuth state; oauth/start usa DB read-only (sin upsert aquí).
    return client_id


async def start_notion_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector
    from duckclaw.mcp_connector_presets import preset_supports_oauth_pkce, resolve_preset_id

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    preset_id = resolve_preset_id(str(connector.get("preset_id") or ""))
    if preset_id != NOTION_PRESET_ID or not preset_supports_oauth_pkce(preset_id):
        raise ValueError("OAuth Notion no está habilitado para esta plantilla MCP")

    callback = resolve_notion_redirect_uri(redirect_uri)
    meta, resource = await discover_notion_oauth_metadata()
    auth_endpoint = str(meta.get("authorization_endpoint") or "").strip()
    if not auth_endpoint:
        raise ValueError("Notion OAuth metadata missing authorization_endpoint")

    client_id = await _resolve_notion_client_id(db, tenant_id=tenant_id, redirect_uri=callback)
    verifier, challenge = _pkce_pair()
    state = _encode_oauth_state(
        {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email,
            "preset_id": NOTION_PRESET_ID,
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
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    query = httpx.QueryParams(params)
    return {
        "authorization_url": f"{auth_endpoint}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def exchange_notion_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    if not all([redirect_uri, code_verifier, client_id]):
        raise ValueError("OAuth pending payload incomplete")
    meta, _ = await discover_notion_oauth_metadata()
    token_endpoint = str(meta.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("Notion OAuth metadata missing token_endpoint")

    token_payload = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            token_endpoint,
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
    "build_oauth_completion_commands",
    "discover_notion_oauth_metadata",
    "exchange_notion_code_for_token",
    "resolve_notion_redirect_uri",
    "start_notion_oauth",
    "_decode_oauth_state",
]
