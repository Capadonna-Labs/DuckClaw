"""Bind per-turn tool context before agent policy early phase."""

from __future__ import annotations

import logging
import time
from typing import Any

from duckclaw.workers.factory_agent_node_helpers import (
    _identity_fields,
    _last_human_message_index,
)
from duckclaw.workers.tool_binding import tool_called_since as _tool_called_since
from langchain_core.messages import AIMessage

_log = logging.getLogger(__name__)


def bind_agent_turn_tool_context(
    *,
    state: dict[str, Any],
    worker_id: str,
    path: str,
    db: Any,
    chat_ctx: str,
    tenant_ctx: str,
) -> None:
    try:
        from duckclaw.forge.skills.goals_tool_context import (
            set_goals_tool_chat_id,
            set_goals_tool_db_path,
            set_goals_tool_worker_id,
        )
        from duckclaw.forge.skills.knowledge_tool_context import (
            set_knowledge_tool_project_id,
            set_knowledge_tool_scope,
            set_knowledge_tool_tenant_id,
            set_knowledge_tool_worker_uid,
            set_session_actor_email,
            set_session_chat_id,
        )

        set_goals_tool_chat_id(str(chat_ctx))
        set_goals_tool_worker_id(worker_id)
        set_goals_tool_db_path(str(path))
        set_knowledge_tool_tenant_id(tenant_ctx)
        project_ctx = str(state.get("project_id") or "")
        set_knowledge_tool_project_id(project_ctx)
        from duckclaw.knowledge_scope import normalize_knowledge_scope

        set_knowledge_tool_scope(
            normalize_knowledge_scope(
                str(state.get("knowledge_scope") or ""),
                project_id=project_ctx,
            )
        )
        worker_uid = ""
        try:
            import duckdb

            con = duckdb.connect(str(path), read_only=True)
            try:
                row = con.execute(
                    """
                    SELECT worker_uid FROM main.admin_worker_catalog
                    WHERE worker_id = ? AND tenant_id = ? AND active = true
                    LIMIT 1
                    """,
                    [worker_id, tenant_ctx],
                ).fetchone()
                if row:
                    worker_uid = str(row[0] or "").strip()
            finally:
                con.close()
        except Exception:
            worker_uid = ""
        set_knowledge_tool_worker_uid(worker_uid)
        set_session_chat_id(str(chat_ctx))
        username = str(state.get("username") or state.get("actor_email") or "").strip()
        set_session_actor_email(username or f"chat:{chat_ctx}")
        try:
            from duckclaw.forge.skills.report_engine_hub_context import set_report_engine_hub_db

            set_report_engine_hub_db(db)
        except Exception:
            pass
    except Exception:
        pass


def maybe_force_get_current_time_orchestration(
    *,
    state: dict[str, Any],
    orch_forced: str | None,
    tools_by_name: dict[str, Any],
    telegram_context_summarize_directive: bool,
    worker_log_label: str,
) -> dict[str, Any] | None:
    if (
        orch_forced != "get_current_time"
        or "get_current_time" not in tools_by_name
        or telegram_context_summarize_directive
    ):
        return None
    last_human_idx = _last_human_message_index(state.get("messages") or [])
    if _tool_called_since(state.get("messages") or [], last_human_idx, "get_current_time"):
        return None
    forced_tid = f"call_orch_get_current_time_{int(time.time() * 1000)}"
    forced_tc = [
        {
            "name": "get_current_time",
            "args": {},
            "id": forced_tid,
            "type": "tool_call",
        }
    ]
    _log.info("[%s] tool_orchestration → get_current_time", worker_log_label)
    out = {
        **state,
        "messages": state["messages"] + [AIMessage(content="", tool_calls=forced_tc)],
    }
    out.update(_identity_fields(state))
    return out
