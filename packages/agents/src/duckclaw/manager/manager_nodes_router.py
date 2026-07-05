"""Router node: team templates and coordinator delegation pool."""

from __future__ import annotations

import os
from typing import Any, Callable

from duckclaw.manager.manager_entry_routes import _is_entry_route_system_event
from duckclaw.manager.manager_vault_config import _agent_config_db_for_vault
from duckclaw.manager.resilience_flow import _initial_replan_state


def build_router_node(
    *,
    db: Any,
    troot: Any,
) -> Callable[[dict], dict]:
    from duckclaw.graphs.on_the_fly_commands import get_effective_team_templates, _resolve_template_id
    from duckclaw.workers.factory import list_workers

    def router_node(state: dict) -> dict:
        """Equipo efectivo: chat > tenant > env > todos. El manager delega según el plan. Preserva incoming/history/chat_id."""
        chat_id = state.get("chat_id") or ""
        tenant_id = state.get("tenant_id") or "default"
        vault_path = (state.get("vault_db_path") or "").strip()
        state_db = _agent_config_db_for_vault(db, vault_path or None)
        available = list(get_effective_team_templates(state_db, chat_id, tenant_id, troot))
        preferred = (os.environ.get("DUCKCLAW_DEFAULT_WORKER_ID") or "").strip()
        assigned = available[0] if available else None
        if preferred and available:
            for wid in available:
                if (wid or "").strip().lower() == preferred.lower():
                    assigned = (wid or "").strip()
                    break
        incoming_r = (state.get("incoming") or state.get("input") or "").strip()
        entry_r = (state.get("entry_worker_id") or "").strip()
        _entry_route_ev = _is_entry_route_system_event(incoming_r)
        _all_disk_r = list_workers(troot, db=db, tenant_id=tenant_id)
        # Multiplex Telegram: si hay ruta HTTP, priorizar siempre el worker de entrada.
        _canon_entry = _resolve_template_id(_all_disk_r, entry_r) if entry_r else None
        coordinator_id: str | None = None
        delegation_pool: list[str] = []
        from duckclaw.workers.orchestrator import effective_delegation_pool, load_orchestrator_config

        orch_cfg = load_orchestrator_config(_canon_entry, troot) if _canon_entry else None
        if orch_cfg:
            coordinator_id = orch_cfg.coordinator_id
            delegation_pool = effective_delegation_pool(
                orch_cfg.orchestrates, available, troot
            )
            if coordinator_id not in delegation_pool:
                delegation_pool = [coordinator_id] + delegation_pool
            assigned = coordinator_id
            available = list(delegation_pool)
        elif _canon_entry:
            if _canon_entry not in available:
                available = list(available) + [_canon_entry]
            available = [_canon_entry] + [w for w in available if w != _canon_entry]
            assigned = _canon_entry
        out: dict[str, Any] = {"assigned_worker_id": assigned, "available_templates": available}
        if coordinator_id:
            out["coordinator_worker_id"] = coordinator_id
            out["delegation_pool"] = delegation_pool
        # Preservar estado para nodos siguientes (por si el grafo hace merge sustituyendo)
        if "incoming" in state:
            out["incoming"] = state["incoming"]
        if "input" in state:
            out["input"] = state["input"]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        if state.get("knowledge_scope"):
            out["knowledge_scope"] = state.get("knowledge_scope")
        if state.get("project_id"):
            out["project_id"] = state.get("project_id")
        if state.get("user_incoming"):
            out["user_incoming"] = state.get("user_incoming")
        _ot = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot:
            out["outbound_telegram_bot_token"] = _ot
        out.update(_initial_replan_state())
        return out

    return router_node
