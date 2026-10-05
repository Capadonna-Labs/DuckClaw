"""Dispatch MCP connector OAuth by preset."""

from __future__ import annotations

import logging
import time
from typing import Any

from duckclaw.mcp_connector_presets import resolve_preset_id

_log = logging.getLogger(__name__)


def persist_mcp_connector_oauth_tokens(
    *,
    tenant_id: str,
    actor_email: str,
    connector_id: str,
    bearer_token: str,
    refresh_token: str = "",
    oauth_client_id: str = "",
    oauth_redirect_uri: str = "",
) -> str:
    """Persist OAuth tokens through DB-Writer; returns the write task_id.

    This used to open the hub RW from the Gateway, which raced DB-Writer
    ("Conflict on tuple deletion"): rotated refresh tokens (Notion, Google) were
    lost, the next refresh got invalid_grant and the connector died until the user
    redid OAuth. Fresh tokens are also kept in-process (see
    ``remember_refreshed_oauth_tokens``) so they work before the write lands.

    When ``oauth_client_id`` is set (Notion/DCR), also store the client that issued the
    tokens so refresh does not reuse a stale DCR client from a previous redirect_uri.
    """
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import SetMcpConnectorAuthCommand

    from duckclaw.admin_mcp_connectors import _REFRESHED_OAUTH

    # Latest tokens win immediately (a re-done OAuth must replace a cached dead pair).
    _REFRESHED_OAUTH[(tenant_id or "default", connector_id)] = (
        bearer_token,
        refresh_token,
        time.time(),
    )
    path = (get_gateway_db_path() or "").strip()
    if not path:
        raise ValueError("Gateway DuckDB path not configured")
    command = SetMcpConnectorAuthCommand(
        tenant_id=tenant_id or "default",
        actor_email=actor_email or "system",
        connector_id=connector_id,
        bearer_token=bearer_token,
        refresh_token=refresh_token,
        oauth_client_id=oauth_client_id,
        oauth_redirect_uri=oauth_redirect_uri,
    )
    try:
        return enqueue_typed_command(command, db_path=path)
    except Exception as exc:
        _log.warning("OAuth token persist enqueue failed connector=%s: %s", connector_id, exc)
        raise RuntimeError(f"No se pudo guardar el token OAuth ({str(exc)[:200]}).") from exc


async def start_mcp_connector_oauth(
    db: Any,
    *,
    connector_id: str,
    tenant_id: str,
    actor_email: str,
    redirect_uri: str | None = None,
) -> dict[str, str]:
    from duckclaw.admin_mcp_connectors import get_mcp_connector

    connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    if not connector:
        raise ValueError(f"connector not found: {connector_id}")
    from duckclaw.mcp_connector_presets import (
        is_google_workspace_preset,
        preset_uses_mcp_dcr,
        resolve_preset_id,
    )

    preset_id = resolve_preset_id(str(connector.get("preset_id") or ""))
    if preset_uses_mcp_dcr(preset_id) and preset_id != "notion":
        from duckclaw.mcp_dcr_oauth import start_dcr_oauth

        return await start_dcr_oauth(
            db,
            connector_id=connector_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            redirect_uri=redirect_uri,
        )
    if preset_id == "notion":
        from duckclaw.mcp_notion_oauth import start_notion_oauth

        return await start_notion_oauth(
            db,
            connector_id=connector_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            redirect_uri=redirect_uri,
        )
    if preset_id == "spotify":
        from duckclaw.mcp_spotify_oauth import start_spotify_oauth

        return await start_spotify_oauth(
            db,
            connector_id=connector_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            redirect_uri=redirect_uri,
        )
    if preset_id == "google_youtube_analytics":
        # No Google-hosted MCP/PRM exists for YouTube — hardcoded endpoints, not discovery.
        from duckclaw.mcp_youtube_oauth import start_youtube_oauth

        return await start_youtube_oauth(
            db,
            connector_id=connector_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            redirect_uri=redirect_uri,
        )
    if is_google_workspace_preset(preset_id):
        from duckclaw.mcp_google_workspace_oauth import start_google_workspace_oauth

        return await start_google_workspace_oauth(
            db,
            connector_id=connector_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            redirect_uri=redirect_uri,
        )
    from duckclaw.mcp_higgsfield_oauth import start_higgsfield_oauth

    return await start_higgsfield_oauth(
        db,
        connector_id=connector_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        redirect_uri=redirect_uri,
    )


async def exchange_mcp_oauth_code_for_token(*, code: str, pending: dict[str, Any]) -> dict[str, str]:
    from duckclaw.mcp_connector_presets import (
        is_google_workspace_preset,
        preset_payload,
        preset_uses_mcp_dcr,
        resolve_preset_id,
    )

    preset_id = resolve_preset_id(str(pending.get("preset_id") or ""))
    if preset_uses_mcp_dcr(preset_id) and preset_id != "notion":
        from duckclaw.mcp_dcr_oauth import exchange_dcr_code_for_token

        endpoint = str(pending.get("endpoint_url") or "").strip()
        if not endpoint:
            payload = preset_payload(preset_id) or {}
            endpoint = str(payload.get("endpoint_url") or "").strip()
        return await exchange_dcr_code_for_token(code=code, pending=pending, endpoint_url=endpoint)
    if preset_id == "notion":
        from duckclaw.mcp_notion_oauth import exchange_notion_code_for_token

        return await exchange_notion_code_for_token(code=code, pending=pending)
    if preset_id == "spotify":
        from duckclaw.mcp_spotify_oauth import exchange_spotify_code_for_token

        return await exchange_spotify_code_for_token(code=code, pending=pending)
    if preset_id == "google_youtube_analytics":
        from duckclaw.mcp_youtube_oauth import exchange_youtube_code_for_token

        return await exchange_youtube_code_for_token(code=code, pending=pending)
    if is_google_workspace_preset(preset_id):
        from duckclaw.mcp_google_workspace_oauth import exchange_google_code_for_token

        return await exchange_google_code_for_token(code=code, pending=pending)
    from duckclaw.mcp_higgsfield_oauth import exchange_oauth_code_for_token

    return await exchange_oauth_code_for_token(code=code, pending=pending)
