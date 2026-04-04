"""Resuelve la ruta DuckDB del tenant para CONTEXT_INJECTION (misma lógica que _invoke_chat)."""

from __future__ import annotations

from pathlib import Path

from duckclaw.gateway_db import resolve_env_duckdb_path
from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved
from duckclaw.vaults import resolve_active_vault, vault_scope_id_for_tenant


def resolve_telegram_user_vault_db_path(
    *,
    tenant_id: str,
    vault_user_id: str,
    telegram_forced_vault_db_path: str | None,
) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    uid = str(vault_user_id or "default").strip() or "default"
    scope = vault_scope_id_for_tenant(tid)
    _, path = resolve_active_vault(uid, scope)
    forced = (telegram_forced_vault_db_path or "").strip()
    if forced:
        return resolve_env_duckdb_path(forced)
    ded = dedicated_gateway_db_path_resolved()
    if ded:
        return str(Path(ded).expanduser().resolve())
    return str(Path(path).expanduser().resolve())
