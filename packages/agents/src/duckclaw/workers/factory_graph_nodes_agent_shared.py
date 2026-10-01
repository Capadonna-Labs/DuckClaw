"""Shared unpack preamble for agent node submodules."""

from __future__ import annotations

import textwrap
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.factory_graph_context import WorkerGraphContext


LLM_THINKING_ROW = "Pensando"
LLM_WRITING_ROW = "Escribiendo respuesta"


def log_llm_usage(
    worker_label: str,
    t0: Optional[float] = None,
    *,
    state: Optional[dict[str, Any]] = None,
    tool_calls: Any = None,
    error: Any = None,
    response: Any = None,
) -> float:
    """``llm_usage:`` console lines (same shape as ``tool_usage:``) + a row in the
    admin Tool Usage box.

    ``t0=None`` logs ``phase=thinking`` and opens a running "Pensando" row; returns
    the start time. With ``t0`` the call finished: ``decided_tools`` / ``writing`` /
    ``error`` + elapsed; a final answer relabels the row "Escribiendo respuesta".
    The invoke is non-streaming, so "writing" is only known once the answer returns.
    """
    import logging
    import time

    log = logging.getLogger("duckclaw.workers.factory_graph_nodes_agent_invoke")
    if t0 is None:
        log.info("llm_usage: worker=%s | phase=thinking", worker_label)
        _publish_llm_row(state, worker_label, "start")
        return time.monotonic()
    phase = "error" if error is not None else ("decided_tools" if tool_calls else "writing")
    elapsed_ms = (time.monotonic() - t0) * 1000
    meta = getattr(response, "response_metadata", None) or {}
    if str(meta.get("finish_reason") or meta.get("stop_reason") or "").lower() in ("length", "max_tokens"):
        # Output budget exhausted (reasoning models count thinking tokens): the reply
        # is cut or empty and the UI falls back to a tool summary ("N registros.").
        usage = (meta.get("token_usage") or {}).get("completion_tokens")
        log.warning(
            "llm_usage: worker=%s | phase=%s | elapsed_ms=%.0f | truncated=max_tokens completion_tokens=%s",
            worker_label, phase, elapsed_ms, usage,
        )
    else:
        log.info("llm_usage: worker=%s | phase=%s | elapsed_ms=%.0f", worker_label, phase, elapsed_ms)
    _publish_llm_row(
        state,
        worker_label,
        "error" if phase == "error" else "done",
        elapsed_ms=elapsed_ms,
        rename=LLM_WRITING_ROW if phase == "writing" else "",
    )
    return t0


def _publish_llm_row(
    state: Optional[dict[str, Any]],
    worker_label: str,
    phase: str,
    *,
    elapsed_ms: Optional[float] = None,
    rename: str = "",
) -> None:
    """Fire-and-forget; admin UI chats only (same gate as tool heartbeats)."""
    chat_id = str((state or {}).get("chat_id") or (state or {}).get("session_id") or "").strip()
    if not chat_id:
        return
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session, publish_admin_chat_heartbeat

        if not is_admin_ui_chat_session(chat_id):
            return
        head = str((state or {}).get("subagent_instance_label") or "").strip() or worker_label
        publish_admin_chat_heartbeat(
            chat_id,
            f"🧠 {LLM_THINKING_ROW}",
            kind="tool",
            worker_id=head or None,
            tool_name=LLM_THINKING_ROW,
            tool_phase=phase,
            elapsed_ms=elapsed_ms,
            tool_rename=rename or None,
        )
    except Exception:
        pass


def load_agent_env(ctx: WorkerGraphContext) -> dict[str, Any]:
    """Execute AGENT_CTX_UNPACK; caller must materialize names for nested closures."""
    env: dict[str, Any] = {"ctx": ctx}
    exec(AGENT_CTX_UNPACK, env)
    return env


AGENT_BINDING_NAMES: tuple[str, ...] = (
    "worker_id",
    "db",
    "spec",
    "path",
    "provider",
    "llm",
    "tool_surface",
    "tools",
    "tools_by_name",
    "tools_sandbox_off",
    "tools_by_name_sandbox_off",
    "prompt_policies",
    "_lid",
    "use_cm",
    "_tools_for_llm_bind",
    "_tools_sandbox_off_bind",
    "_sandbox_enabled_for_state",
    "b",
    "llm_with_tools_on",
    "llm_with_tools_off",
    "llm_force_schema_on",
    "llm_force_schema_off",
    "llm_force_read_sql_on",
    "llm_force_read_sql_off",
    "llm_force_admin_sql_on",
    "llm_force_admin_sql_off",
    "llm_force_run_sandbox_on",
    "llm_force_run_sandbox_off",
    "llm_force_tavily_on",
    "llm_force_tavily_off",
    "llm_force_generate_visual_on",
    "llm_force_generate_visual_off",
    "llm_force_reddit_post_on",
    "llm_force_reddit_post_off",
    "llm_force_reddit_search_on",
    "llm_force_reddit_search_off",
    "llm_force_reddit_fallback_on",
    "llm_force_reddit_fallback_off",
    "has_read_sql",
    "has_tavily",
    "has_generate_visual",
    "primary_visual_tool",
    "has_reddit_tools",
    "has_run_sandbox",
    "_bind_tools",
    "_count_tool_messages_named",
    "_first_reddit_url_in_text",
    "_incoming_has_reddit_share_path",
    "_incoming_has_reddit_url",
    "_incoming_looks_like_reddit_post_url",
    "_is_latest_game_query",
    "_is_schema_query",
    "_patch_ai_reddit_share_tool_calls",
    "_reddit_share_slug_from_incoming",
    "_reddit_tool_message_no_data",
)


def unpack_agent_bindings(agent_env: dict[str, Any]) -> tuple[Any, ...]:
    """Materialize AGENT_CTX_UNPACK keys as a tuple for closure capture."""
    return tuple(agent_env[name] for name in AGENT_BINDING_NAMES)

AGENT_CTX_UNPACK = textwrap.dedent(
    """
    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    path = ctx.path
    provider = ctx.provider
    llm = ctx.llm
    tool_surface = ctx.tool_surface
    tools = ctx.tools
    tools_by_name = ctx.tools_by_name
    tools_sandbox_off = ctx.tools_sandbox_off
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    prompt_policies = ctx.prompt_policies
    _lid = ctx.logical_worker_id
    use_cm = ctx.use_context_monitor
    _tools_for_llm_bind = ctx.tools_for_llm_bind
    _tools_sandbox_off_bind = ctx.tools_sandbox_off_bind
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    b = ctx.agent_bind
    llm_with_tools_on = b.get("llm_with_tools_on")
    llm_with_tools_off = b.get("llm_with_tools_off")
    llm_force_schema_on = b.get("llm_force_schema_on")
    llm_force_schema_off = b.get("llm_force_schema_off")
    llm_force_read_sql_on = b.get("llm_force_read_sql_on")
    llm_force_read_sql_off = b.get("llm_force_read_sql_off")
    llm_force_admin_sql_on = b.get("llm_force_admin_sql_on")
    llm_force_admin_sql_off = b.get("llm_force_admin_sql_off")
    llm_force_run_sandbox_on = b.get("llm_force_run_sandbox_on")
    llm_force_run_sandbox_off = b.get("llm_force_run_sandbox_off")
    llm_force_tavily_on = b.get("llm_force_tavily_on")
    llm_force_tavily_off = b.get("llm_force_tavily_off")
    llm_force_generate_visual_on = b.get("llm_force_generate_visual_on")
    llm_force_generate_visual_off = b.get("llm_force_generate_visual_off")
    llm_force_reddit_post_on = b.get("llm_force_reddit_post_on")
    llm_force_reddit_post_off = b.get("llm_force_reddit_post_off")
    llm_force_reddit_search_on = b.get("llm_force_reddit_search_on")
    llm_force_reddit_search_off = b.get("llm_force_reddit_search_off")
    llm_force_reddit_fallback_on = b.get("llm_force_reddit_fallback_on")
    llm_force_reddit_fallback_off = b.get("llm_force_reddit_fallback_off")
    has_read_sql = b.get("has_read_sql", False)
    has_tavily = b.get("has_tavily", False)
    has_generate_visual = b.get("has_generate_visual", False)
    primary_visual_tool = b.get("primary_visual_tool") or "generate_visual_asset"
    has_reddit_tools = b.get("has_reddit_tools", False)
    has_run_sandbox = b.get("has_run_sandbox", False)
    from duckclaw.integrations.llm_providers import bind_tools_with_parallel_default as _bind_tools
    from duckclaw.workers.factory_graph_agent_reddit_helpers import (
        count_tool_messages_named as _count_tool_messages_named,
        first_reddit_url_in_text as _first_reddit_url_in_text,
        incoming_has_reddit_share_path as _incoming_has_reddit_share_path,
        incoming_has_reddit_url as _incoming_has_reddit_url,
        incoming_looks_like_reddit_post_url as _incoming_looks_like_reddit_post_url,
        is_latest_game_query as _is_latest_game_query,
        is_schema_query as _is_schema_query,
        patch_ai_reddit_share_tool_calls as _patch_ai_reddit_share_tool_calls,
        reddit_share_slug_from_incoming as _reddit_share_slug_from_incoming,
        reddit_tool_message_no_data as _reddit_tool_message_no_data,
    )
"""
).strip() + "\n"
