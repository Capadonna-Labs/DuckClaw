"""Dispatch MCP connector OAuth by preset."""

from __future__ import annotations

from typing import Any

from duckclaw.mcp_connector_presets import resolve_preset_id


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
    if is_google_workspace_preset(preset_id):
        from duckclaw.mcp_google_workspace_oauth import exchange_google_code_for_token

        return await exchange_google_code_for_token(code=code, pending=pending)
    from duckclaw.mcp_higgsfield_oauth import exchange_oauth_code_for_token

    return await exchange_oauth_code_for_token(code=code, pending=pending)
