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
) -> str:
    """Persist OAuth tokens synchronously; ponytail: async queue alone loses tokens on DuckDB lock."""
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import SetMcpConnectorAuthCommand
    from duckclaw.write_handlers.mcp_connectors import _apply_set_mcp_connector_auth

    payload = {
        "tenant_id": tenant_id,
        "actor_email": actor_email,
        "connector_id": connector_id,
        "bearer_token": bearer_token,
        "refresh_token": refresh_token,
    }
    path = (get_gateway_db_path() or "").strip()
    if not path:
        raise ValueError("Gateway DuckDB path not configured")

    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            db = DuckClaw(path, read_only=False, engine="python")
            try:
                _apply_set_mcp_connector_auth(db, payload)
            finally:
                db.close()
            return ""
        except Exception as exc:
            last_exc = exc
            if "lock" not in str(exc).lower() or attempt >= 3:
                break
            time.sleep(0.15 * (attempt + 1))

    _log.warning(
        "OAuth token sync persist failed connector=%s: %s; enqueue fallback",
        connector_id,
        last_exc,
    )
    from duckclaw.gateway_enqueue import enqueue_admin_command

    task_id = enqueue_admin_command(SetMcpConnectorAuthCommand(**payload))
    return task_id


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
    from duckclaw.mcp_connector_presets import is_google_workspace_preset, resolve_preset_id

    preset_id = resolve_preset_id(str(connector.get("preset_id") or ""))
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
    from duckclaw.mcp_connector_presets import is_google_workspace_preset, resolve_preset_id

    preset_id = resolve_preset_id(str(pending.get("preset_id") or ""))
    if preset_id == "notion":
        from duckclaw.mcp_notion_oauth import exchange_notion_code_for_token

        return await exchange_notion_code_for_token(code=code, pending=pending)
    if preset_id == "spotify":
        from duckclaw.mcp_spotify_oauth import exchange_spotify_code_for_token

        return await exchange_spotify_code_for_token(code=code, pending=pending)
    if is_google_workspace_preset(preset_id):
        from duckclaw.mcp_google_workspace_oauth import exchange_google_code_for_token

        return await exchange_google_code_for_token(code=code, pending=pending)
    from duckclaw.mcp_higgsfield_oauth import exchange_oauth_code_for_token

    return await exchange_oauth_code_for_token(code=code, pending=pending)
