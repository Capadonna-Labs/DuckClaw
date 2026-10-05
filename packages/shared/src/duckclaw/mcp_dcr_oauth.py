"""OAuth PKCE for hosted MCP servers that publish PRM and dynamic client registration.

Cursor's Nexlev entry is only a URL. The client discovers the authorization
server and registers a public client. No client secret is stored in env.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from duckclaw.mcp_higgsfield_oauth import (
    OAUTH_CLIENT_DOMAIN,
    _encode_oauth_state,
    _pkce_pair,
    resolve_oauth_redirect_uri,
)


def protected_resource_metadata_url(endpoint_url: str) -> str:
    """RFC 9728 PRM URL. The MCP path is the suffix after the well-known segment."""
    parsed = urlparse((endpoint_url or "").strip().rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("endpoint_url inválida para OAuth MCP")
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{parsed.path or ''}"


def _auth_base(pr_data: Any) -> str:
    if not isinstance(pr_data, dict):
        raise ValueError("invalid protected resource metadata")
    auth_servers = pr_data.get("authorization_servers")
    if not isinstance(auth_servers, list) or not auth_servers:
        raise ValueError("protected resource missing authorization_servers")
    return str(auth_servers[0]).rstrip("/")


def _json_mapping(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("invalid OAuth metadata")
    return data


async def discover_dcr_oauth_metadata(endpoint_url: str) -> tuple[dict[str, Any], str]:
    prm_url = protected_resource_metadata_url(endpoint_url)
    async with httpx.AsyncClient(timeout=20.0) as client:
        pr_data = _json_mapping(await client.get(prm_url))
        meta = _json_mapping(
            await client.get(f"{_auth_base(pr_data)}/.well-known/oauth-authorization-server")
        )
    resource = str(pr_data.get("resource") or endpoint_url).strip()
    return meta, resource


def discover_dcr_oauth_metadata_sync(endpoint_url: str) -> dict[str, Any]:
    prm_url = protected_resource_metadata_url(endpoint_url)
    pr_data = _json_mapping(httpx.get(prm_url, timeout=12.0))
    meta_url = f"{_auth_base(pr_data)}/.well-known/oauth-authorization-server"
    return _json_mapping(httpx.get(meta_url, timeout=12.0))


def _load_dcr_client_id(db: Any, *, tenant_id: str, preset_id: str, redirect_uri: str) -> str:
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    row = resolve_runtime_setting(
        db,
        tenant_id=tenant_id,
        actor_email="",
        domain=OAUTH_CLIENT_DOMAIN,
        key=f"{preset_id}.client_id",
    )
    client_id = str(row.get("value_text") or row.get("value") or "").strip()
    meta = row.get("value_json")
    stored_redirect = str(meta.get("redirect_uri") or "").strip() if isinstance(meta, dict) else ""
    if client_id and stored_redirect == redirect_uri:
        return client_id
    return ""


async def _register_dcr_client(*, redirect_uri: str, registration_endpoint: str) -> str:
    payload = {
        "client_name": "DuckClaw Admin",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        data = _json_mapping(await client.post(registration_endpoint, json=payload))
    client_id = str(data.get("client_id") or "").strip()
    if not client_id:
        raise ValueError("OAuth registration missing client_id")
    return client_id


async def _resolve_dcr_client_id(
    db: Any | None,
    *,
    tenant_id: str,
    preset_id: str,
    redirect_uri: str,
    endpoint_url: str,
) -> str:
    if db is not None:
        cached = _load_dcr_client_id(
            db, tenant_id=tenant_id, preset_id=preset_id, redirect_uri=redirect_uri
        )
        if cached:
            return cached
    meta, _ = await discover_dcr_oauth_metadata(endpoint_url)
    registration_endpoint = str(meta.get("registration_endpoint") or "").strip()
    if not registration_endpoint:
        raise ValueError("OAuth metadata missing registration_endpoint")
    # ponytail: client_id va en OAuth state; oauth/start usa DB read-only (sin upsert aquí).
    return await _register_dcr_client(
        redirect_uri=redirect_uri,
        registration_endpoint=registration_endpoint,
    )


async def start_dcr_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector
    from duckclaw.mcp_connector_presets import preset_supports_oauth_pkce, preset_uses_mcp_dcr, resolve_preset_id

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    preset_id = resolve_preset_id(str(connector.get("preset_id") or ""))
    if not preset_uses_mcp_dcr(preset_id) or not preset_supports_oauth_pkce(preset_id):
        raise ValueError("OAuth por descubrimiento no está habilitado para esta plantilla MCP")
    endpoint_url = str(connector.get("endpoint_url") or "").strip()
    if not endpoint_url:
        raise ValueError("connector missing endpoint_url")
    callback = resolve_oauth_redirect_uri(redirect_uri)
    meta, resource = await discover_dcr_oauth_metadata(endpoint_url)
    auth_endpoint = str(meta.get("authorization_endpoint") or "").strip()
    if not auth_endpoint:
        raise ValueError("OAuth metadata missing authorization_endpoint")
    client_id = await _resolve_dcr_client_id(
        db,
        tenant_id=tenant_id,
        preset_id=preset_id,
        redirect_uri=callback,
        endpoint_url=endpoint_url,
    )
    return _authorization_result(
        connector_id=connector_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        preset_id=preset_id,
        endpoint_url=endpoint_url,
        resource=resource,
        auth_endpoint=auth_endpoint,
        client_id=client_id,
        callback=callback,
    )


def _authorization_result(
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    preset_id: str,
    endpoint_url: str,
    resource: str,
    auth_endpoint: str,
    client_id: str,
    callback: str,
) -> dict[str, str]:
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
            "endpoint_url": endpoint_url,
            "created_at": time.time(),
        }
    )
    query = httpx.QueryParams(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        }
    )
    return {
        "authorization_url": f"{auth_endpoint}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def exchange_dcr_code_for_token(
    *,
    code: str,
    pending: dict[str, Any],
    endpoint_url: str,
) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    if not all([redirect_uri, code_verifier, client_id, endpoint_url]):
        raise ValueError("OAuth pending payload incomplete")
    meta, _ = await discover_dcr_oauth_metadata(endpoint_url)
    token_endpoint = str(meta.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("OAuth metadata missing token_endpoint")
    return await _post_token(
        token_endpoint,
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
    )


async def _post_token(token_endpoint: str, payload: dict[str, str]) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(token_endpoint, data=payload, headers={"Accept": "application/json"})
    if resp.status_code >= 400:
        raise ValueError(f"token exchange failed: {resp.status_code} {resp.text[:300]}")
    tokens = resp.json()
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("token response missing access_token")
    return {
        "access_token": access_token,
        "refresh_token": str(tokens.get("refresh_token") or "").strip(),
    }


def refresh_dcr_access_token(
    refresh_token: str,
    *,
    endpoint_url: str,
    client_id: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    """Public DCR clients refresh with client_id and refresh_token. No client secret."""
    refresh = (refresh_token or "").strip()
    cid = (client_id or "").strip()
    if not refresh or not cid or not (endpoint_url or "").strip():
        return {}
    meta = discover_dcr_oauth_metadata_sync(endpoint_url)
    token_endpoint = str(meta.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("OAuth metadata missing token_endpoint")
    payload = _refresh_payload(refresh, cid, redirect_uri)
    resp = httpx.post(
        token_endpoint,
        data=payload,
        headers={"Accept": "application/json"},
        timeout=20.0,
    )
    if resp.status_code >= 400:
        raise ValueError(f"oauth refresh failed: {resp.status_code} {resp.text[:300]}")
    tokens = resp.json() if resp.content else {}
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("oauth refresh missing access_token")
    rotated = str(tokens.get("refresh_token") or "").strip() or refresh
    return {"access_token": access_token, "refresh_token": rotated}


def _refresh_payload(refresh: str, client_id: str, redirect_uri: str | None) -> dict[str, str]:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
    }
    redir = (redirect_uri or "").strip()
    if redir:
        payload["redirect_uri"] = redir
    return payload
