"""Agent early.py phase."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.utils.logger import format_chat_log_identity, set_log_context
from duckclaw.workers.db_intent_policy import incoming_is_table_content_query as _incoming_is_table_content_query
from duckclaw.workers.factory_agent_node_helpers import (
    _identity_fields,
    _is_visual_generation_tool,
    _last_human_message_index,
    _raise_if_chat_cancelled_from_state,
    _visual_asset_calls_since_last_human,
    _worker_log_label,
)
from duckclaw.workers.factory_reddit_helpers import (
    _reddit_tools_paused,
    _resolve_reddit_share_url_to_comments_url,
)
from duckclaw.workers.runtime_policy_helpers import worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool
from duckclaw.workers.tool_binding import tool_called_since as _tool_called_since
from duckclaw.workers.tool_invocation_policy import (
    decide_current_time_tool_invocation as _decide_current_time_tool_invocation,
    decide_db_first_tool_invocation as _decide_db_first_tool_invocation,
)
from duckclaw.workers.tool_surface_policy import tool_surface_intent_text
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.factory_graph_nodes_agent_policy_early_context import (
    bind_agent_turn_tool_context,
    maybe_force_get_current_time_orchestration,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_agent_shared import load_agent_env, unpack_agent_bindings

_log = logging.getLogger(__name__)


def make_agent_policy_early(ctx: WorkerGraphContext):
    (
        worker_id, db, spec, path, provider, llm, tool_surface,
        tools, tools_by_name, tools_sandbox_off, tools_by_name_sandbox_off, prompt_policies, _lid,
        use_cm, _tools_for_llm_bind, _tools_sandbox_off_bind, _sandbox_enabled_for_state, b,
        llm_with_tools_on, llm_with_tools_off, llm_force_schema_on, llm_force_schema_off,
        llm_force_read_sql_on, llm_force_read_sql_off, llm_force_admin_sql_on, llm_force_admin_sql_off,
        llm_force_run_sandbox_on, llm_force_run_sandbox_off, llm_force_tavily_on, llm_force_tavily_off,
        llm_force_generate_visual_on, llm_force_generate_visual_off, llm_force_reddit_post_on,
        llm_force_reddit_post_off, llm_force_reddit_search_on, llm_force_reddit_search_off,
        llm_force_reddit_fallback_on, llm_force_reddit_fallback_off, has_read_sql, has_tavily,
        has_generate_visual, primary_visual_tool, has_reddit_tools, has_run_sandbox, _bind_tools, _count_tool_messages_named, _first_reddit_url_in_text,
        _incoming_has_reddit_share_path, _incoming_has_reddit_url, _incoming_looks_like_reddit_post_url,
        _is_latest_game_query, _is_schema_query, _patch_ai_reddit_share_tool_calls,
        _reddit_share_slug_from_incoming, _reddit_tool_message_no_data,
    ) = unpack_agent_bindings(load_agent_env(ctx))

    def run(state: dict, config: Optional[RunnableConfig] = None) -> dict | None:
                _raise_if_chat_cancelled_from_state(state)
                if state.get("visual_evidence_graph_retry"):
                    state = {**state, "visual_evidence_graph_retry": False}
                _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
                _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
                _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
                set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
                bind_agent_turn_tool_context(
                    state=state,
                    worker_id=worker_id,
                    path=str(path),
                    db=db,
                    chat_ctx=str(_chat_ctx),
                    tenant_ctx=_tenant_ctx,
                )
                _wl = _worker_log_label(worker_id)
                cfg = config or {}
                incoming = (
                    (state.get("incoming") or state.get("input") or "").strip()
                    or (cfg.get("configurable") or {}).get("incoming") or ""
                )
                if isinstance(incoming, str):
                    incoming = incoming.strip()
                else:
                    incoming = str(incoming or "").strip()
                # Fallback: extraer del último HumanMessage
                if not incoming and state.get("messages"):
                    for m in reversed(state["messages"]):
                        if isinstance(m, HumanMessage) and getattr(m, "content", None):
                            incoming = (str(m.content) or "").strip()
                            break
                _intent_incoming = tool_surface_intent_text(state.get("user_incoming"), incoming)
                telegram_context_summarize_directive = (
                    "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in (incoming or "")
                    or "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
                )
                summarize_stored_directive = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
                _is_goals_tick_msg = (
                    str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                    and proactive_review_event_phrase_in_text(str(incoming or ""))
                )
                if _is_goals_tick_msg:
                    try:
                        from duckclaw.homeostasis.goals_alignment import (
                            alignment_review_phrase_in_text,
                            pick_nudge_opener,
                        )
                        from duckclaw.graphs.chat_heartbeat import publish_admin_chat_heartbeat

                        if alignment_review_phrase_in_text(str(incoming or "")):
                            publish_admin_chat_heartbeat(
                                str(_chat_ctx),
                                pick_nudge_opener(str(_chat_ctx), time.time()),
                                kind="alignment",
                                worker_id=worker_id,
                            )
                    except Exception:
                        pass
                is_schema = _is_schema_query(_intent_incoming)
                is_table_content = _incoming_is_table_content_query(_intent_incoming)
                is_latest_game = _is_latest_game_query(_intent_incoming)
                # Resumen post /context --add | --summary: el volcado ya va en el mensaje; no forzar inspect_schema
                # (p. ej. "esquemas criptográficos" dispara is_schema por subcadena "esquema"), read_sql, Reddit, etc.
                # SUMMARIZE_STORED_CONTEXT suele incluir URLs (reddit.com/...): sin esto, force_reddit roba el turno
                # y el modelo nunca sintetiza el snapshot de main.semantic_memory.
                if telegram_context_summarize_directive:
                    is_schema = False
                    is_table_content = False
                    is_latest_game = False
                # No forzar herramienta si el último mensaje ya es ToolMessage (ya ejecutamos la tool):
                # así el LLM puede responder con texto y no entrar en bucle (inspect_schema -> agent -> inspect_schema).
                last_msg = (state.get("messages") or [])[-1] if state.get("messages") else None
                already_has_tool_result = last_msg is not None and isinstance(last_msg, ToolMessage)

                _orch = None
                _orch_forced: str | None = None
                _orch_incoming = (state.get("user_incoming") or "").strip() or incoming
                try:
                    from duckclaw.workers.tool_orchestration import (
                        parse_tool_orchestration,
                        resolve_forced_tool,
                    )

                    _orch = parse_tool_orchestration(spec)
                    if _orch and not telegram_context_summarize_directive:
                        _orch_forced = resolve_forced_tool(
                            _orch,
                            _orch_incoming,
                            state.get("messages") or [],
                            tools_by_name,
                        )
                except Exception:
                    _orch = None
                    _orch_forced = None

                _orch_forced_out = maybe_force_get_current_time_orchestration(
                    state=state,
                    orch_forced=_orch_forced,
                    tools_by_name=tools_by_name,
                    telegram_context_summarize_directive=telegram_context_summarize_directive,
                    worker_log_label=_wl,
                )
                if _orch_forced_out is not None:
                    return _orch_forced_out

                db_first_tool_decision = _decide_db_first_tool_invocation(
                    spec=spec,
                    incoming=incoming,
                    available_tools=tools_by_name,
                    already_has_tool_result=already_has_tool_result,
                    summarize_directive=telegram_context_summarize_directive,
                    orchestration_active=bool(_orch),
                )

                force_schema = is_schema and not already_has_tool_result
                force_admin_sql = bool(
                    _orch_forced == "admin_sql"
                    or db_first_tool_decision.is_tool("admin_sql")
                )
                force_read_sql = bool(
                    _orch_forced == "read_sql"
                    or db_first_tool_decision.is_tool("read_sql")
                    or (
                        (
                            is_table_content
                            or is_latest_game
                        )
                        and not already_has_tool_result
                    )
                )
                force_tavily = False

                _reddit_anchor_u: Optional[str] = None
                if _incoming_has_reddit_url(incoming):
                    _reddit_anchor_u = _first_reddit_url_in_text(incoming)
                incoming_for_reddit = incoming
                if _reddit_anchor_u and (_reddit_anchor_u not in (incoming or "")):
                    incoming_for_reddit = f"{incoming}\n{_reddit_anchor_u}"

                _reddit_resolved_comments_url: Optional[str] = None
                if _reddit_anchor_u and _incoming_has_reddit_share_path(_reddit_anchor_u):
                    _reddit_resolved_comments_url = _resolve_reddit_share_url_to_comments_url(_reddit_anchor_u)
                if _reddit_resolved_comments_url:
                    incoming_for_reddit = (
                        f"{incoming_for_reddit}\nCanonical Reddit thread: {_reddit_resolved_comments_url}"
                    )

                share_slug = _reddit_share_slug_from_incoming(incoming_for_reddit)
                reddit_search_tool_count = _count_tool_messages_named(state.get("messages") or [], "reddit_search_reddit")
                need_share_followup = bool(
                    share_slug
                    and already_has_tool_result
                    and isinstance(last_msg, ToolMessage)
                    and (last_msg.name or "") == "reddit_search_reddit"
                    and share_slug not in str(last_msg.content or "")
                    and reddit_search_tool_count < 2
                    and not _reddit_tool_message_no_data(last_msg)
                )
                # SUMMARIZE_NEW_CONTEXT con solo URL de Reddit debe poder forzar Reddit (fetch); STORED con URLs en
                # el volcado no debe robar el turno (sintetizar snapshot DuckDB).
                if (
                    _reddit_tools_paused()
                    and _reddit_anchor_u
                    and _incoming_has_reddit_url(incoming)
                    and not already_has_tool_result
                ):
                    _paused_ai = AIMessage(
                        content=(
                            "🔴 Reddit pausado (`DUCKCLAW_REDDIT_PAUSED=1`). "
                            "No se invocaron herramientas reddit_* en este turno."
                        )
                    )
                    _out_rp = {**state, "messages": state["messages"] + [_paused_ai]}
                    _out_rp.update(_identity_fields(state))
                    return _out_rp
                _visual_calls_this_turn = _visual_asset_calls_since_last_human(state.get("messages") or [])
                _visual_tool_already_ok = bool(
                    already_has_tool_result
                    and isinstance(last_msg, ToolMessage)
                    and _is_visual_generation_tool(last_msg.name or "")
                    and '"ok":true' in str(last_msg.content or "").replace(" ", "")
                )
                force_visual = bool(
                    has_generate_visual
                    and tool_surface == "visual_generation"
                    and not telegram_context_summarize_directive
                    and not summarize_stored_directive
                    and _visual_calls_this_turn == 0
                    and not already_has_tool_result
                    and not _visual_tool_already_ok
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                    )
                )
                _visual_tool_failed = bool(
                    already_has_tool_result
                    and isinstance(last_msg, ToolMessage)
                    and _is_visual_generation_tool(last_msg.name or "")
                    and '"ok":false' in str(last_msg.content or "").replace(" ", "")
                )
                if _visual_tool_failed:
                    err_msg = "No pude generar la imagen."
                    try:
                        payload = json.loads(str(last_msg.content or ""))
                        if isinstance(payload, dict) and payload.get("error"):
                            err_msg = str(payload["error"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                    if "cancelad" in err_msg.lower():
                        err_msg = (
                            f"{err_msg} Si enviaste otro mensaje mientras generaba, "
                            "espera a que termine ComfyUI (~3 min en Mac) antes de escribir de nuevo."
                        )
                    _fail_ai = AIMessage(content=f"⚠️ {err_msg}")
                    _out_fail = {**state, "messages": state["messages"] + [_fail_ai]}
                    _out_fail.update(_identity_fields(state))
                    return _out_fail

                if _visual_tool_already_ok:
                    caption = "Imagen generada."
                    try:
                        payload = json.loads(str(last_msg.content or ""))
                        if isinstance(payload, dict):
                            caption = str(payload.get("message") or caption).strip() or caption
                    except (json.JSONDecodeError, TypeError):
                        pass
                    _ok_ai = AIMessage(content=caption)
                    _out_ok = {**state, "messages": state["messages"] + [_ok_ai]}
                    _out_ok.update(_identity_fields(state))
                    return _out_ok

                _allow_reddit_force = bool(
                    _incoming_has_reddit_url(incoming)
                    or (telegram_context_summarize_directive and _reddit_anchor_u)
                )
                force_reddit = bool(
                    not force_visual
                    and not _reddit_tools_paused()
                    and
                    _allow_reddit_force
                    and has_reddit_tools
                    and _reddit_anchor_u is not None
                    and not summarize_stored_directive
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                    )
                    and (not already_has_tool_result or need_share_followup)
                )
                # Tras 2× reddit_search_reddit en /s/… el MCP suele seguir sin el hilo correcto; si no cortamos,
                # el LLM re-invoca reddit_search en bucle (evidencia: pm2 logs 13:52, forced_tool=auto).
                _reddit_share_mcp_exhausted = bool(
                    _worker_use_heuristic_first_tool(spec)
                    and _allow_reddit_force
                    and bool(share_slug)
                    and bool(_reddit_anchor_u)
                    and _incoming_has_reddit_share_path(str(_reddit_anchor_u))
                    and reddit_search_tool_count >= 2
                )

                if not _worker_use_heuristic_first_tool(spec):
                    force_schema = False
                    force_admin_sql = False
                    if not (
                        db_first_tool_decision.is_tool("read_sql")
                        and not db_first_tool_decision.requires_heuristic_first_tool
                    ):
                        force_read_sql = False
                    force_tavily = False
                    force_reddit = False
                    force_visual = False

                force_orch_tool: str | None = None
                if _orch_forced and _orch_forced != "get_current_time":
                    if _orch_forced == "read_sql" and force_read_sql:
                        pass
                    elif _orch_forced == "admin_sql" and force_admin_sql:
                        pass
                    else:
                        from duckclaw.workers.tool_orchestration import (
                            _first_bindable_tool,
                            _last_human_index,
                            _tools_since,
                        )

                        _orch_candidates = [_orch_forced]
                        if _orch and _orch_forced in (
                            "execute_sandbox_script",
                            "run_sandbox",
                        ):
                            _orch_candidates = [
                                "execute_sandbox_script",
                                "run_sandbox",
                            ]
                        _orch_msgs = state.get("messages") or []
                        _orch_lh = _last_human_index(list(_orch_msgs))
                        _orch_ran = set(_tools_since(list(_orch_msgs), _orch_lh))
                        _bindable_orch = _first_bindable_tool(
                            _orch_candidates,
                            tools_by_name,
                            _orch_ran,
                        )
                        if _bindable_orch:
                            force_orch_tool = _bindable_orch
                            if force_orch_tool != "read_sql":
                                force_read_sql = False
                        elif _orch_forced in (
                            "execute_sandbox_script",
                            "run_sandbox",
                        ):
                            _log.warning(
                                "[%s] orchestration wanted sandbox tool %s but none bindable; tools=%s",
                                _wl,
                                _orch_forced,
                                sorted(
                                    n
                                    for n in tools_by_name
                                    if "sandbox" in n or n == "execute_sandbox_script"
                                ),
                            )

                from duckclaw.workers.tool_orchestration import (
                    find_gmail_mcp_search_tool,
                    incoming_has_email_intent,
                )

                _email_intent = incoming_has_email_intent(_orch_incoming)
                _gmail_search_tool = (
                    find_gmail_mcp_search_tool(tools_by_name) if _email_intent else None
                )
                if (
                    _gmail_search_tool
                    and _worker_use_heuristic_first_tool(spec)
                    and not already_has_tool_result
                    and not force_orch_tool
                    and not telegram_context_summarize_directive
                    and not summarize_stored_directive
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                        or force_visual
                        or force_reddit
                    )
                ):
                    force_orch_tool = _gmail_search_tool

                ctx.agent_turn = {'_intent_incoming': _intent_incoming, '_orch': _orch, '_orch_forced': _orch_forced, '_reddit_resolved_comments_url': _reddit_resolved_comments_url, '_reddit_share_mcp_exhausted': _reddit_share_mcp_exhausted, '_visual_tool_already_ok': _visual_tool_already_ok, '_wl': _wl, 'already_has_tool_result': already_has_tool_result, 'force_admin_sql': force_admin_sql, 'force_orch_tool': force_orch_tool, 'force_read_sql': force_read_sql, 'force_reddit': force_reddit, 'force_schema': force_schema, 'force_tavily': force_tavily, 'force_visual': force_visual, 'incoming': incoming, 'incoming_for_reddit': incoming_for_reddit, 'is_latest_game': is_latest_game, 'is_schema': is_schema, 'is_table_content': is_table_content, 'reddit_search_tool_count': reddit_search_tool_count, 'state': state, 'summarize_stored_directive': summarize_stored_directive, 'telegram_context_summarize_directive': telegram_context_summarize_directive}
                return None

    return run
