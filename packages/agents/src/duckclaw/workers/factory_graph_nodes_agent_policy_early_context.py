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
            set_goals_tool_tenant_id,
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
        set_goals_tool_tenant_id(tenant_ctx)
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


def apply_terminal_force_tool_overrides(
    *,
    incoming: str,
    orch_incoming: str,
    intent_incoming: str,
    tools_by_name: dict[str, Any],
    called_tools_since_last_human: set[str] | frozenset[str],
    already_has_tool_result: bool,
    telegram_context_summarize_directive: bool,
    summarize_stored_directive: bool,
    use_heuristic_first_tool: bool,
    force_orch_tool: str | None,
    force_schema: bool,
    force_admin_sql: bool,
    force_read_sql: bool,
    force_tavily: bool,
    force_reddit: bool,
    force_visual: bool,
    homeostasis_streak: int = 0,
    db: Any | None = None,
    chat_id: str | None = None,
) -> tuple[str | None, bool, bool, bool, bool, bool, bool]:
    """Email then /loop homeostasis overrides (clear competing force_* flags).

    Email/Gmail wins over db-first / orch read_sql noise on EVERY hop.
    Hop 1: force Gmail search. Hop 2+: still clear read_sql — otherwise
    orch re-forces SELECT now() AS ahora and set_reply falls back to
    "1 registro (ahora…)." after a successful get_message.
    """
    from duckclaw.workers.tool_invocation_policy import (
        decide_loop_homeostasis_tool_invocation,
        _is_loop_or_proactive_system_event,
    )
    from duckclaw.workers.tool_orchestration import (
        find_gmail_mcp_search_tool,
        incoming_has_email_intent,
    )

    streak = int(homeostasis_streak or 0)
    if streak <= 0 and db is not None and chat_id:
        try:
            from duckclaw.commands.loop_state_keys import (
                LOOP_HOMEOSTASIS_STREAK_KEY,
                get_loop_chat_state,
            )

            streak = int(
                (get_loop_chat_state(db, chat_id, LOOP_HOMEOSTASIS_STREAK_KEY) or "0").strip() or "0"
            )
        except Exception:
            streak = 0

    email_intent = incoming_has_email_intent(
        orch_incoming or intent_incoming or incoming
    )
    gmail_search_tool = (
        find_gmail_mcp_search_tool(tools_by_name) if email_intent else None
    )
    # On /loop ticks, never force Gmail — trading sensors first.
    if _is_loop_or_proactive_system_event(incoming):
        gmail_search_tool = None
    if (
        gmail_search_tool
        and not telegram_context_summarize_directive
        and not summarize_stored_directive
    ):
        force_schema = False
        force_admin_sql = False
        force_read_sql = False
        force_tavily = False
        force_reddit = False
        force_visual = False
        if force_orch_tool in ("read_sql", "admin_sql", "inspect_schema"):
            force_orch_tool = None
        if not already_has_tool_result and use_heuristic_first_tool:
            force_orch_tool = gmail_search_tool

    decision = decide_loop_homeostasis_tool_invocation(
        incoming=incoming,
        available_tools=tools_by_name,
        called_tools_since_last_human=called_tools_since_last_human,
        already_has_tool_result=already_has_tool_result,
        summarize_directive=telegram_context_summarize_directive,
        homeostasis_streak=streak,
    )
    if decision.should_force and decision.tool_name:
        force_orch_tool = decision.tool_name
        force_schema = False
        force_admin_sql = False
        force_read_sql = False
        force_tavily = False
        force_reddit = False
        force_visual = False

    # Root: after evaluate_homeostasis on a /loop tick, never re-force SQL/noise.
    # Otherwise db-first / is_table_content keeps forcing read_sql until the 900s
    # wall timeout and the UI surfaces Binder Error as the "answer".
    called = {str(n) for n in called_tools_since_last_human}
    if (
        _is_loop_or_proactive_system_event(incoming)
        and "evaluate_homeostasis" in called
        and not decision.should_force
    ):
        force_schema = False
        force_admin_sql = False
        force_read_sql = False
        force_tavily = False
        force_reddit = False
        force_visual = False
        orch = str(force_orch_tool or "").strip()
        if orch in (
            "",
            "read_sql",
            "admin_sql",
            "inspect_schema",
            "evaluate_homeostasis",
            "get_ibkr_portfolio",
            "get_ibkr_open_orders",
            "get_ibkr_order_history",
        ) or orch.startswith(("mcp__", "android_")):
            force_orch_tool = None

    return (
        force_orch_tool,
        force_schema,
        force_admin_sql,
        force_read_sql,
        force_tavily,
        force_reddit,
        force_visual,
    )
