"""Resolución de bóveda DuckDB para un turno de chat."""

from __future__ import annotations

from core.gateway_vault import dedicated_gateway_vault_db_path
from core.models import ChatRequest
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.gateway_db import resolve_env_duckdb_path
from duckclaw.vaults import resolve_active_vault, vault_scope_id_for_tenant


def resolve_chat_vault_db_path(
    *,
    payload: ChatRequest,
    worker_id: str,
    vault_user_id: str,
    tenant_id: str,
    delivery_context: GatewayDeliveryContext,
) -> tuple[str, str | None]:
    """
    Returns:
        (vault_db_path, telegram_guard_acl_db_path) — la segunda solo si difiere del hub.
    """
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    _, vault_db_path = resolve_active_vault(vault_user_id, vault_scope)
    telegram_acl_for_guard: str | None = None

    forced_v = (delivery_context.telegram_forced_vault_db_path or "").strip()
    payload_vault = (getattr(payload, "vault_db_path", None) or "").strip()
    if forced_v:
        vault_db_path = resolve_env_duckdb_path(forced_v)
        telegram_acl_for_guard = vault_db_path
    elif payload_vault:
        vault_db_path = resolve_env_duckdb_path(payload_vault)
        telegram_acl_for_guard = vault_db_path
    else:
        dedicated = dedicated_gateway_vault_db_path()
        if dedicated:
            vault_db_path = dedicated

    if not forced_v and not payload_vault:
        route_wid = (worker_id or "").strip()
        if route_wid:
            try:
                from duckclaw.vaults import resolve_template_vault_path
                from duckclaw.workers.manifest import load_manifest

                spec_route = load_manifest(route_wid)
                tpl_path = resolve_template_vault_path(
                    spec_route.forge_vault_binding, vault_user_id
                )
                if tpl_path:
                    vault_db_path = tpl_path
            except Exception:
                pass

    return vault_db_path, telegram_acl_for_guard
