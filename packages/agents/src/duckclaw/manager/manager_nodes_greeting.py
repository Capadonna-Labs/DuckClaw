"""Greeting and capabilities fast-path node."""

from __future__ import annotations

from typing import Any, Callable

from duckclaw.graphs.state import ManagerAgentState
from duckclaw.manager.fast_replies import (
    _capabilities_fast_reply_text,
    _greeting_fast_reply_text,
    _knowledge_inventory_fast_reply_text,
    _manager_capabilities_fast_path_ok,
    _manager_knowledge_inventory_fast_path_ok,
)
from duckclaw.manager.manager_vault_config import _agent_config_db_for_vault
from duckclaw.manager.task_activity import _append_task_audit_safely
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_sys, set_log_context


def build_greeting_shortcut_node(
    *,
    db: Any,
) -> Callable[[ManagerAgentState], ManagerAgentState]:
    from duckclaw.graphs.on_the_fly_commands import append_task_audit

    _obs = get_obs_logger()

    def greeting_shortcut_node(state: ManagerAgentState) -> ManagerAgentState:
        """Responde saludos o preguntas «qué puedes hacer» sin plan ni invoke_worker."""
        chat_id = state.get("chat_id") or ""
        tenant_id = (state.get("tenant_id") or "default").strip() or "default"
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        user_text = (state.get("user_incoming") or incoming).strip()
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        _cid = (chat_id or "").strip() or "unknown"
        set_log_context(
            tenant_id=tenant_id,
            worker_id="manager",
            chat_id=format_chat_log_identity(_cid, state.get("username")),
        )
        coord = (state.get("coordinator_worker_id") or "").strip() or None
        pool = list(state.get("delegation_pool") or [])
        username = str(state.get("username") or state.get("actor_email") or "").strip() or None
        _vault_path_reply = (state.get("vault_db_path") or "").strip()
        _reply_policy_db = _agent_config_db_for_vault(db, _vault_path_reply or None)
        if _manager_knowledge_inventory_fast_path_ok(user_text):
            log_sys(_obs, "Inventario RAG: respuesta directa (sin plan ni subagente)")
            project_id = str(state.get("project_id") or "").strip()
            knowledge_scope = str(state.get("knowledge_scope") or "platform").strip() or "platform"
            worker_uid = ""
            reply = _knowledge_inventory_fast_reply_text(
                _reply_policy_db,
                tenant_id=tenant_id,
                project_id=project_id,
                worker_uid=worker_uid,
                knowledge_scope=knowledge_scope,
                worker_id=assigned,
                username=username,
            )
            _audit_title = "Inventario RAG (respuesta directa)"
        elif _manager_capabilities_fast_path_ok(user_text):
            log_sys(_obs, "Capacidades: respuesta directa (sin plan ni subagente)")
            reply = _capabilities_fast_reply_text(
                assigned,
                tenant_id=tenant_id,
                coordinator_id=coord,
                delegation_pool=pool,
                prompt_policies=PromptPolicyResolver(_reply_policy_db),
                username=username,
            )
            _audit_title = "Capacidades (respuesta directa)"
        else:
            log_sys(_obs, "Saludo: respuesta directa (sin plan ni subagente)")
            reply = _greeting_fast_reply_text(assigned, tenant_id=tenant_id, username=username)
            _audit_title = "Saludo directo"
        _append_task_audit_safely(
            append_task_audit,
            db=db,
            chat_id=chat_id,
            worker_id=assigned or "manager",
            incoming=incoming,
            status="SUCCESS",
            elapsed_ms=0,
            plan_title=_audit_title,
        )
        out: ManagerAgentState = {
            "reply": reply,
            "_audit_done": True,
            "assigned_worker_id": assigned,
            "plan_title": None,
            "incoming": incoming,
            "input": incoming,
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
        if state.get("coordinator_worker_id"):
            out["coordinator_worker_id"] = state.get("coordinator_worker_id")
        if state.get("delegation_pool"):
            out["delegation_pool"] = state.get("delegation_pool")
        if state.get("knowledge_scope"):
            out["knowledge_scope"] = state.get("knowledge_scope")
        if state.get("project_id"):
            out["project_id"] = state.get("project_id")
        _ot_g = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_g:
            out["outbound_telegram_bot_token"] = _ot_g
        return out

    return greeting_shortcut_node
