"""OAuth PKCE for Google official remote Workspace MCP servers (gmailmcp.googleapis.com, etc.)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

_log = logging.getLogger(__name__)

_log = logging.getLogger(__name__)

from duckclaw.mcp_higgsfield_oauth import (
    _decode_oauth_state,
    _encode_oauth_state,
    _pkce_pair,
    build_oauth_completion_commands,
    resolve_oauth_redirect_uri,
)

GOOGLE_OIDC_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_WORKSPACE_OAUTH_PROVIDER = "google_workspace"


def resolve_google_redirect_uri(explicit: str | None = None) -> str:
    # ponytail: Google exige match exacto con URI registrada en GCP; env gana sobre origin del Admin (:8443).
    env_redirect = (os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if env_redirect:
        return env_redirect.rstrip("/")
    explicit_clean = (explicit or "").strip()
    if explicit_clean:
        return explicit_clean.rstrip("/")
    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    if public:
        return f"{public}/api/v1/oauth/callback"
    admin = (os.environ.get("DUCKCLAW_ADMIN_URL") or "").strip().rstrip("/")
    if admin:
        parsed = urlparse(admin)
        if parsed.scheme and parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}/api/v1/oauth/callback"
    return resolve_oauth_redirect_uri(explicit)


def protected_resource_metadata_url(endpoint_url: str) -> str:
    """RFC 9728 PRM URL for Google hosted MCP (path suffix matches MCP path)."""
    parsed = urlparse(endpoint_url.strip().rstrip("/"))
    path = parsed.path or ""
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{path}"


def _google_client_credentials() -> tuple[str, str]:
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET son obligatorios")
    return client_id, client_secret


def _normalize_scopes(scopes: list[Any]) -> str:
    cleaned: list[str] = []
    for item in scopes:
        scope = str(item or "").strip()
        if scope and scope not in cleaned:
            cleaned.append(scope)
    if "openid" not in cleaned:
        cleaned.insert(0, "openid")
    return " ".join(cleaned)


def resolve_google_oauth_scopes(prm_scopes: list[Any], *, read_only: bool = True) -> str:
    """PRM lista scopes write+read; conector read_only pide solo *.readonly (ponytail)."""
    override = (os.environ.get("GOOGLE_OAUTH_SCOPES") or "").strip()
    if override:
        return _normalize_scopes(override.replace(",", " ").split())
    items = [str(x).strip() for x in prm_scopes if str(x).strip()]
    if read_only and any(s.endswith(".readonly") for s in items):
        items = [s for s in items if s == "openid" or s.endswith(".readonly")]
    return _normalize_scopes(items)


async def discover_google_mcp_oauth(
    endpoint_url: str,
    *,
    read_only: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Fetch PRM + OIDC metadata; returns (oidc_meta, prm, resource, scope_string)."""
    prm_url = protected_resource_metadata_url(endpoint_url)
    async with httpx.AsyncClient(timeout=20.0) as client:
        pr_resp = await client.get(prm_url)
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()
        if not isinstance(pr_data, dict):
            raise ValueError("invalid google MCP protected resource metadata")
        auth_servers = pr_data.get("authorization_servers")
        if not isinstance(auth_servers, list) or not auth_servers:
            raise ValueError("google MCP PRM missing authorization_servers")
        auth_base = str(auth_servers[0]).rstrip("/")
        oidc_url = f"{auth_base}/.well-known/openid-configuration"
        if auth_base.rstrip("/") == "https://accounts.google.com":
            oidc_url = GOOGLE_OIDC_METADATA_URL
        meta_resp = await client.get(oidc_url)
        meta_resp.raise_for_status()
        oidc = meta_resp.json()
        if not isinstance(oidc, dict):
            raise ValueError("invalid google OIDC metadata")
    resource = str(pr_data.get("resource") or endpoint_url.strip()).strip()
    scopes_raw = pr_data.get("scopes_supported")
    if isinstance(scopes_raw, list) and scopes_raw:
        scope_string = resolve_google_oauth_scopes(scopes_raw, read_only=read_only)
    else:
        scope_string = "openid email profile"
    return oidc, pr_data, resource, scope_string


async def start_google_workspace_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector
    from duckclaw.mcp_connector_presets import (
        is_google_workspace_preset,
        preset_google_oauth_scopes,
        preset_supports_oauth_pkce,
    )

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    preset_id = str(connector.get("preset_id") or "")
    if not is_google_workspace_preset(preset_id) or not preset_supports_oauth_pkce(preset_id):
        raise ValueError("OAuth Google Workspace no está habilitado para esta plantilla MCP")

    endpoint_url = str(connector.get("endpoint_url") or "").strip()
    if not endpoint_url:
        raise ValueError("connector missing endpoint_url")

    read_only = connector.get("read_only")
    if read_only is None:
        read_only = True
    callback = resolve_google_redirect_uri(redirect_uri)
    oidc, prm, resource, scope_string = await discover_google_mcp_oauth(
        endpoint_url,
        read_only=bool(read_only),
    )
    preset_scopes = preset_google_oauth_scopes(preset_id)
    if preset_scopes:
        scope_string = _normalize_scopes(preset_scopes)
    auth_endpoint = str(oidc.get("authorization_endpoint") or "").strip()
    if not auth_endpoint:
        raise ValueError("Google OIDC metadata missing authorization_endpoint")

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
            "endpoint_url": endpoint_url,
            "resource": resource,
            "scope": scope_string,
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
        "resource": resource,
    }
    query = httpx.QueryParams(params)
    return {
        "authorization_url": f"{auth_endpoint}?{query}",
        "state": state,
        "redirect_uri": callback,
    }


async def exchange_google_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    redirect_uri = str(pending.get("redirect_uri") or "")
    code_verifier = str(pending.get("code_verifier") or "")
    client_id = str(pending.get("client_id") or "")
    endpoint_url = str(pending.get("endpoint_url") or "")
    if not all([redirect_uri, code_verifier, client_id, endpoint_url]):
        raise ValueError("OAuth pending payload incomplete")
    _, client_secret = _google_client_credentials()
    oidc, _, discovered_resource, _ = await discover_google_mcp_oauth(endpoint_url)
    token_endpoint = str(oidc.get("token_endpoint") or "").strip()
    if not token_endpoint:
        raise ValueError("Google OIDC metadata missing token_endpoint")

    resource = str(pending.get("resource") or discovered_resource or "").strip()
    token_payload = {
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    if resource:
        token_payload["resource"] = resource
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


def refresh_google_access_token(refresh_token: str) -> str:
    """Exchange Google refresh_token for a fresh access_token."""
    refresh = (refresh_token or "").strip()
    if not refresh:
        return ""
    client_id, client_secret = _google_client_credentials()
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error")
            except Exception:
                err = None
            _log.warning("google oauth refresh failed: %s %s", resp.status_code, err or resp.text[:120])
            return ""
        tokens = resp.json()
    access = str(tokens.get("access_token") or "").strip()
    return access


__all__ = [
    "GOOGLE_WORKSPACE_OAUTH_PROVIDER",
    "build_oauth_completion_commands",
    "discover_google_mcp_oauth",
    "exchange_google_code_for_token",
    "protected_resource_metadata_url",
    "refresh_google_access_token",
    "resolve_google_redirect_uri",
    "start_google_workspace_oauth",
    "_decode_oauth_state",
]
