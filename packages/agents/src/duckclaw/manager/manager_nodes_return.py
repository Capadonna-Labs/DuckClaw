"""Return-to-source node after A2A mission handoff."""

from __future__ import annotations

from typing import Any, Callable

from duckclaw.graphs.state import ManagerAgentState
from duckclaw.manager.manager_vault_config import (
    _agent_config_db_for_vault,
    _load_manager_task_policy,
)
from duckclaw.manager.routing import _worker_matches_id
from duckclaw.prompt_policies import PromptPolicyResolver


def build_return_to_source_node(
    *,
    db: Any,
) -> Callable[[ManagerAgentState], ManagerAgentState]:

    def return_to_source_node(state: ManagerAgentState) -> ManagerAgentState:
        mission = state.get("active_mission")
        if not isinstance(mission, dict):
            return {"active_mission": None}  # type: ignore[return-value]
        source_worker = (mission.get("source_worker") or "").strip()
        if not source_worker:
            return {"active_mission": None}  # type: ignore[return-value]

        source_in_team = None
        available = state.get("available_templates") or []
        for wid in available:
            if _worker_matches_id(wid, source_worker):
                source_in_team = wid
                break
        next_worker = source_in_team or source_worker

        mission_result = (state.get("last_worker_raw_reply") or state.get("reply") or "").strip()
        mission_name = (mission.get("mission") or "mission").strip() or "mission"
        _return_policy_db = _agent_config_db_for_vault(
            db,
            (state.get("vault_db_path") or "").strip() or None,
        )
        _return_prompt_policies = PromptPolicyResolver(_return_policy_db)
        target_worker = (mission.get("target_worker") or "").strip() or "subagente"
        mission_system_message = (
            f"El worker {target_worker} completó la misión {mission_name}. "
            f"Resultado crudo: {mission_result}\n\n"
            "Sintetiza el resultado para el usuario sin inventar datos."
        )
        synthesis_task = _load_manager_task_policy(
            _return_prompt_policies,
            "mission_return_synthesis",
            mission_name=mission_name,
            mission_result=mission_result,
            target_worker=target_worker,
        )
        if not synthesis_task:
            synthesis_task = mission_result or mission_name

        out: ManagerAgentState = {
            "assigned_worker_id": next_worker,
            "planned_task": synthesis_task,
            "incoming": synthesis_task,
            "input": synthesis_task,
            "mission_context_system_message": mission_system_message,
            "active_mission": None,
            "handoff_context": None,
        }  # type: ignore[assignment]
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
        if "available_templates" in state:
            out["available_templates"] = state["available_templates"]
        if state.get("user_incoming"):
            out["user_incoming"] = state.get("user_incoming")
        if state.get("entry_worker_id"):
            out["entry_worker_id"] = state.get("entry_worker_id")
        if "plan_title" in state:
            out["plan_title"] = state["plan_title"]
        if "tasks" in state:
            out["tasks"] = state["tasks"]
        if "task_summary" in state:
            out["task_summary"] = state["task_summary"]
        _tok_rs = (state.get("outbound_telegram_bot_token") or "").strip()
        if _tok_rs:
            out["outbound_telegram_bot_token"] = _tok_rs
        return out

    return return_to_source_node
