"""Vault-scoped agent config and manager task policy resolution."""

from __future__ import annotations

from typing import Any

from duckclaw.prompt_policies import PromptPolicyResolver


def _load_manager_task_policy(
    prompt_policies: PromptPolicyResolver | None,
    policy_name: str,
    **kwargs: str,
) -> str | None:
    """Resuelve manager_task desde DuckDB sin fallback Markdown."""
    if prompt_policies is None:
        return None
    try:
        if kwargs:
            return prompt_policies.format("manager_task", policy_name, **kwargs)
        return prompt_policies.load("manager_task", policy_name)
    except (FileNotFoundError, RuntimeError):
        return None


def _agent_config_db_for_vault(hub_db: Any, vault_db_path: str | None) -> Any:
    """
    Lee claves por chat (team_templates, sandbox_enabled, llm_*) desde el vault del tenant
    cuando existe; si no, desde el hub ``hub_db``. Evita mezclar equipos del hub multiplex
    con rutas que comparten chat_id pero usan otro .duckdb.

    Si vault y hub son el mismo archivo, reutilizar ``hub_db``: ``GatewayDbEphemeralReadonly``
    abre RO efímero y choca con el handle RW del manager en perfil Spawn (mismo PID).
    """
    vp = (vault_db_path or "").strip()
    if vp and vp != ":memory:":
        hub_path = str(getattr(hub_db, "_path", "") or "").strip()
        if hub_path:
            from duckclaw.workers.factory import _same_duckdb_file

            if _same_duckdb_file(hub_path, vp):
                return hub_db
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly

        return GatewayDbEphemeralReadonly(vp)
    return hub_db


__all__ = ["_agent_config_db_for_vault", "_load_manager_task_policy"]
