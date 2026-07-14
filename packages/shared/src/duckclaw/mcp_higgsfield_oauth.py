"""OAuth PKCE for Higgsfield hosted MCP (mcp.higgsfield.ai)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any

import httpx

_log = logging.getLogger(__name__)

HIGGSFIELD_OAUTH_METADATA_URL = "https://mcp.higgsfield.ai/.well-known/oauth-authorization-server"
HIGGSFIELD_MCP_RESOURCE = "https://mcp.higgsfield.ai/mcp"
HIGGSFIELD_PRESET_ID = "higgsfield"

OAUTH_CLIENT_DOMAIN = "mcp_oauth"
PENDING_TTL_SEC = 600
OAUTH_SCOPES = "openid email offline_access"


def resolve_oauth_redirect_uri(explicit: str | None = None) -> str:
    """Public callback URL registered with Higgsfield (Admin BFF or gateway)."""
    override = (explicit or os.environ.get("DUCKCLAW_MCP_OAUTH_REDIRECT_URI") or "").strip()
    if override:
        return override.rstrip("/")
    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return f"{public}/api/v1/admin/mcp/connectors/oauth/callback"
    admin = (os.environ.get("DUCKCLAW_ADMIN_URL") or "").strip().rstrip("/")
    if admin:
        return f"{admin}/api/admin/mcp/connectors/oauth/callback"
    return "http://127.0.0.1:3001/api/admin/mcp/connectors/oauth/callback"


def _oauth_state_secret() -> bytes:
    raw = (
        os.environ.get("DUCKCLAW_MCP_OAUTH_STATE_SECRET")
        or os.environ.get("DUCKCLAW_ADMIN_API_KEY")
        or "duckclaw-dev-oauth"
    ).strip()
    return raw.encode("utf-8")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _encode_oauth_state(payload: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(_oauth_state_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _decode_oauth_state(state: str) -> dict[str, Any]:
    token = (state or "").strip()
    if "." not in token:
        raise ValueError("OAuth state malformed")
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_oauth_state_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("OAuth state signature invalid")
    pad = "=" * (-len(body) % 4)
    raw = json.loads(base64.urlsafe_b64decode(body + pad).decode("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("OAuth state payload invalid")
    created = float(raw.get("created_at") or 0)
    if not created or (time.time() - created) > PENDING_TTL_SEC:
        raise ValueError("OAuth state expired")
    return raw


async def _fetch_oauth_metadata() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(HIGGSFIELD_OAUTH_METADATA_URL)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("invalid oauth metadata")
        return data


async def _register_oauth_client(*, redirect_uri: str, registration_endpoint: str) -> str:
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
        raise ValueError("oauth registration missing client_id")
    return client_id


def _load_oauth_client_id(db: Any, *, tenant_id: str, redirect_uri: str) -> str:
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    row = resolve_runtime_setting(
        db,
        tenant_id=tenant_id,
        actor_email="",
        domain=OAUTH_CLIENT_DOMAIN,
        key=f"{HIGGSFIELD_PRESET_ID}.client_id",
    )
    client_id = str(row.get("value_text") or row.get("value") or "").strip()
    meta = row.get("value_json")
    stored_redirect = ""
    if isinstance(meta, dict):
        stored_redirect = str(meta.get("redirect_uri") or "").strip()
    if client_id and stored_redirect == redirect_uri:
        return client_id
    return ""


async def _resolve_oauth_client_id(
    db: Any | None,
    *,
    tenant_id: str,
    redirect_uri: str,
) -> str:
    if db is not None:
        cached = _load_oauth_client_id(db, tenant_id=tenant_id, redirect_uri=redirect_uri)
        if cached:
            return cached
    meta = await _fetch_oauth_metadata()
    registration_endpoint = str(meta.get("registration_endpoint") or "").strip()
    if not registration_endpoint:
        raise ValueError("Higgsfield OAuth metadata missing registration_endpoint")
    return await _register_oauth_client(
        redirect_uri=redirect_uri,
        registration_endpoint=registration_endpoint,
    )


async def start_higgsfield_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    """Begin OAuth PKCE; returns browser authorization URL (no DB writes)."""
    from duckclaw.admin_mcp_connectors import get_mcp_connector

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    from duckclaw.mcp_connector_presets import preset_supports_oauth_pkce

    preset_id = str(connector.get("preset_id") or "")
    if not preset_supports_oauth_pkce(preset_id):
        raise ValueError("OAuth PKCE no está habilitado para esta plantilla MCP")

    callback = resolve_oauth_redirect_uri(redirect_uri)
    meta = await _fetch_oauth_metadata()
    auth_endpoint = str(meta.get("authorization_endpoint") or "").strip()
    if not auth_endpoint:
        raise ValueError("Higgsfield OAuth metadata missing authorization_endpoint")

    client_id = await _resolve_oauth_client_id(db, tenant_id=tenant_id, redirect_uri=callback)
    verifier, challenge = _pkce_pair()
    state = _encode_oauth_state(
        {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email,
            "preset_id": preset_id or "remote_http_oauth",
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
        "scope": OAUTH_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": HIGGSFIELD_MCP_RESOURCE,
    }
    query = httpx.QueryParams(params)
    return {
        "authorization_url": f"{auth_endpoint}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def complete_higgsfield_oauth(db: Any, *, code: str, state: str) -> dict[str, Any]:
    """Exchange authorization code and persist MCP session token."""
    pending = _decode_oauth_state(state)

    tenant_id = str(pending.get("tenant_id") or "default")
    connector_id = str(pending.get("connector_id") or "")
    actor_email = str(pending.get("actor_email") or "system")
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    if not all([connector_id, redirect_uri, code_verifier, client_id]):
        raise ValueError("OAuth pending payload incomplete")

    meta = await _fetch_oauth_metadata()
    token_endpoint = str(meta.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("Higgsfield OAuth metadata missing token_endpoint")

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
    if not access_token:
        raise ValueError("token response missing access_token")

    from duckclaw.write_handlers.mcp_connectors import _apply_set_mcp_connector_auth

    _apply_set_mcp_connector_auth(
        db,
        {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "actor_email": actor_email,
            "bearer_token": access_token,
        },
    )

    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if refresh_token:
        from duckclaw.admin_runtime_settings import upsert_runtime_setting

        upsert_runtime_setting(
            db,
            tenant_id=tenant_id,
            actor_email="",
            domain=OAUTH_CLIENT_DOMAIN,
            key=f"{connector_id}.refresh",
            value_text=refresh_token,
            secret=True,
            updated_by=actor_email,
        )

    return {"ok": True, "connector_id": connector_id}


def build_oauth_completion_commands(*, code: str, state: str) -> dict[str, Any]:
    """Build auth payload from OAuth callback without touching DuckDB (for enqueue)."""
    pending = _decode_oauth_state(state)
    return {
        "code": code.strip(),
        "pending": pending,
    }


async def exchange_oauth_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    meta = await _fetch_oauth_metadata()
    token_endpoint = str(meta.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("Higgsfield OAuth metadata missing token_endpoint")
    token_payload = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(token_endpoint, data=token_payload, headers={"Accept": "application/json"})
        if resp.status_code >= 400:
            raise ValueError(f"token exchange failed: {resp.status_code} {resp.text[:300]}")
        tokens = resp.json()
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not access_token:
        raise ValueError("token response missing access_token")
    return {"access_token": access_token, "refresh_token": refresh_token}
