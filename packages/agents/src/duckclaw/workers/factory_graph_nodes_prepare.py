"""prepare_node and sandbox session checker."""

from __future__ import annotations

from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.context_monitor import compose_context_summary_prompt as _compose_context_summary_prompt
from duckclaw.workers.db_intent_policy import is_no_task as _is_no_task
from duckclaw.workers.factory_agent_node_helpers import _identity_fields
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.provider_input_budget import apply_provider_input_budget as _apply_provider_input_budget
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def make_prepare_node(ctx: WorkerGraphContext):

    effective_prompt = ctx.effective_prompt
    _context_prompt_base = ctx.context_prompt_base
    provider = ctx.provider

    def prepare_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        cfg = config or {}
        conf_obj = cfg.get("configurable")
        meta = cfg.get("metadata") or {}
        conf_incoming = (conf_obj.get("incoming") if isinstance(conf_obj, dict) else None) or (meta.get("incoming") if meta else None)
        incoming = (
            (state.get("incoming") or state.get("input") or "").strip()
            or (str(conf_incoming).strip() if conf_incoming else "")
        )
        if not incoming and state.get("messages"):
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage) and getattr(m, "content", None):
                    incoming = (str(m.content) or "").strip()
                    break
        if not isinstance(incoming, str):
            incoming = str(incoming or "").strip()
        if _context_prompt_base is not None:
            prompt = _compose_context_summary_prompt(
                _context_prompt_base,
                (state.get("analytical_summary") or state.get("context_summary") or "").strip(),
            )
        else:
            prompt = effective_prompt
        messages = [SystemMessage(content=prompt)]
        for h in (state.get("history") or []):
            role = (h.get("role") or "").lower()
            content = h.get("content") or ""
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        needs_task = state.get("homeostasis_hint") == "ask_task" or _is_no_task(incoming)
        if needs_task:
            user_content = (
                f"[El usuario dijo: '{incoming.strip() or '(vacío)'}'. No ha indicado una tarea concreta. "
                "Pregúntale: ¿Cuál es mi tarea? Y ofrece ejemplos de lo que puedes hacer según tu rol.]"
            )
        else:
            user_content = incoming
        messages.append(HumanMessage(content=user_content))
        messages = _apply_provider_input_budget(messages, provider=provider)
        # LangGraph puede reemplazar/limitar el state entre nodos; preservamos chat_id para
        # que _sandbox_enabled_for_state (y otros flags por sesión) lean el ID correcto.
        out = {**state, "messages": messages, "incoming": incoming}
        if (state.get("analytical_summary") or "").strip():
            out["analytical_summary"] = (state.get("analytical_summary") or "").strip()
        out.update(_identity_fields(state))
        return out

    return prepare_node


def make_sandbox_enabled_for_state(ctx: WorkerGraphContext):
    db = ctx.db

    def _sandbox_enabled_for_state(state: dict) -> bool:
        """Sandbox flag per chat/session (defaults OFF; ON for admin UI si no hay override)."""
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
        from duckclaw.runtime_session_settings import resolve_session_runtime_setting

        chat_id = state.get("chat_id") or state.get("session_id") or "default"
        tenant_id = str(state.get("tenant_id") or "default").strip() or "default"
        raw = resolve_session_runtime_setting(
            db,
            chat_id,
            "sandbox_enabled",
            tenant_id=tenant_id,
        )
        v = (raw or "").strip().lower()
        if not v and is_admin_ui_chat_session(str(chat_id)):
            return True
        return v in ("true", "1", "on", "sí", "si")

    return _sandbox_enabled_for_state
