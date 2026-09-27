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
    """Persist OAuth tokens via the singleton DB-Writer (never open a hub write from Gateway).

    Opening ``DuckClaw(read_only=False)`` from the Gateway process races the
    existing read-only hub handle → ``Can't open a connection to same database
    file with a different configuration``. When Notion rotates ``refresh_token``
    on refresh and that write is lost, the next cycle gets ``invalid_grant`` and
    the connector looks "not configured". Gmail often keeps the old refresh
    usable, which is why it appeared to persist while Notion did not.

    Returns the write ``task_id`` (empty string only for the rare inline-spawn path).
    """
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.gateway_enqueue import enqueue_admin_command
    from duckclaw.write_commands import SetMcpConnectorAuthCommand

    path = (get_gateway_db_path() or "").strip()
    if not path:
        raise ValueError("Gateway DuckDB path not configured")

    command = SetMcpConnectorAuthCommand(
        tenant_id=tenant_id,
        actor_email=actor_email or "system",
        connector_id=connector_id,
        bearer_token=bearer_token,
        refresh_token=refresh_token,
        oauth_client_id=oauth_client_id,
        oauth_redirect_uri=oauth_redirect_uri,
    )
    try:
        return enqueue_admin_command(command, user_id=str(actor_email or "system"))
    except Exception as exc:
        _log.warning(
            "OAuth token enqueue failed connector=%s; trying sync fallback: %s",
            connector_id,
            exc,
        )

    # Fallback for unit tests / spawn-inline / Redis down: direct writer apply.
    # Still avoid competing with an open Gateway RO handle when possible.
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            from duckclaw import DuckClaw
            from duckclaw.write_handlers.mcp_connectors import _apply_set_mcp_connector_auth

            db = DuckClaw(path, read_only=False, engine="python")
            try:
                _apply_set_mcp_connector_auth(
                    db,
                    {
                        "tenant_id": tenant_id,
                        "actor_email": actor_email,
                        "connector_id": connector_id,
                        "bearer_token": bearer_token,
                        "refresh_token": refresh_token,
                        "oauth_client_id": oauth_client_id,
                        "oauth_redirect_uri": oauth_redirect_uri,
                    },
                )
            finally:
                db.close()
            return command.task_id
        except Exception as sync_exc:
            last_exc = sync_exc
            if "lock" not in str(sync_exc).lower() and "different configuration" not in str(
                sync_exc
            ).lower():
                break
            time.sleep(0.15 * (attempt + 1))

    _log.warning(
        "OAuth token sync persist failed connector=%s: %s",
        connector_id,
        last_exc,
    )
    detail = str(last_exc or "persist failed")[:200]
    if "lock" in detail.lower() or "different configuration" in detail.lower():
        msg = f"No se pudo guardar el token OAuth ({detail}). Reintenta en unos segundos."
    else:
        msg = f"No se pudo guardar el token OAuth ({detail})."
    raise RuntimeError(msg) from last_exc


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
    from duckclaw.mcp_connector_presets import is_google_workspace_preset, resolve_preset_id

    preset_id = resolve_preset_id(str(pending.get("preset_id") or ""))
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
