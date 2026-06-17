"""Agent node LLM invoke tail."""

from __future__ import annotations

import logging
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.egress.tool_response_repair import (
    clock_only_lone_url_no_repair as _clock_only_lone_url_no_repair,
    latest_tool_json_since as _latest_tool_json_since,
    parse_get_current_time_json as _parse_get_current_time_json,
    post_tools_synthesis_needed as _post_tools_synthesis_needed,
    reply_is_tool_json_echo as _reply_is_tool_json_echo,
)
from duckclaw.forge.rag.prompt_policy import rag_turn_system_prompt
from duckclaw.forge.rag.tool_policy import (
    should_prioritize_rag_over_storage_tools,
    without_storage_tools,
)
from duckclaw.workers.db_intent_policy import explicit_duckdb_schema_request
from duckclaw.workers.factory_agent_node_helpers import (
    _agent_node_llm_failure_user_message,
    _identity_fields,
    _last_human_message_index,
    _raise_if_chat_cancelled_from_state,
    _worker_log_label,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_agent_policy_early import make_agent_policy_early
from duckclaw.workers.factory_graph_nodes_agent_policy_late import make_agent_policy_late
from duckclaw.workers.factory_graph_nodes_agent_shared import AGENT_CTX_UNPACK
from duckclaw.workers.factory_reddit_helpers import _patch_reddit_get_post_args_from_canonical_url
from duckclaw.workers.provider_input_budget import apply_provider_input_budget as _apply_provider_input_budget
from duckclaw.workers.runtime_policy_helpers import worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool
from duckclaw.workers.tool_surface_policy import (
    should_hide_sandbox_tools,
    should_hide_storage_identity_tools,
    without_privileged_mutation_tools,
    without_sandbox_tools,
    without_storage_identity_tools,
)
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

_log = logging.getLogger(__name__)


def make_agent_invoke_node(ctx: WorkerGraphContext):
    exec(AGENT_CTX_UNPACK, {"ctx": ctx}, locals())
    _early = make_agent_policy_early(ctx)
    _late = make_agent_policy_late(ctx)


def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
    hit = _early(state, config)
    if hit is not None:
        return hit
    hit = _late(state, config)
    if hit is not None:
        return hit
        _intent_incoming = ctx.agent_turn['_intent_incoming']
        _orch = ctx.agent_turn['_orch']
        _reddit_resolved_comments_url = ctx.agent_turn['_reddit_resolved_comments_url']
        _reddit_share_mcp_exhausted = ctx.agent_turn['_reddit_share_mcp_exhausted']
        _visual_tool_already_ok = ctx.agent_turn['_visual_tool_already_ok']
        _wl = ctx.agent_turn['_wl']
        already_has_tool_result = ctx.agent_turn['already_has_tool_result']
        force_admin_sql = ctx.agent_turn['force_admin_sql']
        force_fetch_market_data = ctx.agent_turn['force_fetch_market_data']
        force_read_sql = ctx.agent_turn['force_read_sql']
        force_reddit = ctx.agent_turn['force_reddit']
        force_run_sandbox = ctx.agent_turn['force_run_sandbox']
        force_schema = ctx.agent_turn['force_schema']
        force_tavily = ctx.agent_turn['force_tavily']
        force_visual = ctx.agent_turn['force_visual']
        incoming = ctx.agent_turn['incoming']
        incoming_for_reddit = ctx.agent_turn['incoming_for_reddit']
        is_latest_game = ctx.agent_turn['is_latest_game']
        is_schema = ctx.agent_turn['is_schema']
        is_table_content = ctx.agent_turn['is_table_content']
        reddit_search_tool_count = ctx.agent_turn['reddit_search_tool_count']
        sandbox_enabled = ctx.agent_turn['sandbox_enabled']
        state = ctx.agent_turn['state']
        summarize_stored_directive = ctx.agent_turn['summarize_stored_directive']
        telegram_context_summarize_directive = ctx.agent_turn['telegram_context_summarize_directive']
        llm_with_tools = llm_with_tools_on if sandbox_enabled else llm_with_tools_off
        forced_name = "auto"
        if force_admin_sql:
            forced_name = "admin_sql"
        elif force_read_sql:
            forced_name = "read_sql"
        elif force_schema:
            forced_name = "inspect_schema"
        elif force_visual:
            forced_name = "generate_visual_asset"
        elif force_tavily:
            forced_name = "tavily_search"
        elif force_reddit:
            forced_name = "reddit"
        elif force_fetch_market_data:
            forced_name = "fetch_market_data"
        elif force_run_sandbox:
            forced_name = "run_sandbox"
        _log.info(
            "[%s] incoming=%r | is_schema=%s | is_table_content=%s | is_latest_game=%s | forced_tool=%s",
            _wl,
            incoming[:80] + ("..." if len(incoming) > 80 else ""),
            is_schema,
            is_table_content,
            is_latest_game,
            forced_name,
        )
        from duckclaw.utils.formatters import sanitize_reddit_tool_messages_for_llm

        _msg_list = sanitize_reddit_tool_messages_for_llm(list(state["messages"]))
        if not _worker_use_heuristic_first_tool(spec):
            _msg_list = [
                SystemMessage(content=prompt_policies.load("directive", "tool_choice_generic"))
            ] + _msg_list
        if _reddit_share_mcp_exhausted:
            _msg_list = [
                SystemMessage(content=prompt_policies.load("directive", "reddit_share_exhausted"))
            ] + _msg_list
        if _visual_tool_already_ok:
            _msg_list = [
                SystemMessage(
                    content=(
                        "La imagen ya fue generada con generate_visual_asset en este turno. "
                        "Responde al usuario con la ruta/artefacto; NO vuelvas a llamar "
                        "generate_visual_asset ni edit_visual_asset."
                    )
                )
            ] + _msg_list
        _reddit_ctx_block: Optional[str] = None
        if _reddit_http_prefetch_ctx and not already_has_tool_result:
            _reddit_ctx_block = _reddit_http_prefetch_ctx
        if not _reddit_ctx_block:
            for _rm in reversed(_msg_list):
                if isinstance(_rm, ToolMessage) and str(getattr(_rm, "name", "") or "").startswith(
                    "reddit_"
                ):
                    from duckclaw.utils.formatters import build_reddit_llm_context_block

                    _reddit_ctx_block = build_reddit_llm_context_block(str(_rm.content or ""))
                    break
        if _reddit_ctx_block:
            _msg_list = [SystemMessage(content=_reddit_ctx_block)] + _msg_list
        _rag_turn_without_db_intent = should_prioritize_rag_over_storage_tools(
            incoming,
            _intent_incoming,
            explicit_storage_request=explicit_duckdb_schema_request,
        )
        if _rag_turn_without_db_intent:
            _msg_list = [
                SystemMessage(content=rag_turn_system_prompt(prompt_policies, _lid))
            ] + [m for m in _msg_list if not isinstance(m, SystemMessage)]
        _groq_msgs = _apply_provider_input_budget(_msg_list, provider=provider)
        _invoked_llm: Any = llm_with_tools
        if force_admin_sql:
            _fa = llm_force_admin_sql_on if sandbox_enabled else llm_force_admin_sql_off
            _invoked_llm = _fa or llm_with_tools
        elif force_schema and not force_read_sql:
            _invoked_llm = (
                llm_force_schema_on if sandbox_enabled else llm_force_schema_off
            )
        elif force_read_sql:
            _invoked_llm = (
                llm_force_read_sql_on if sandbox_enabled else llm_force_read_sql_off
            )
        elif force_tavily:
            _ft = llm_force_tavily_on if sandbox_enabled else llm_force_tavily_off
            _invoked_llm = _ft or llm_with_tools
        elif force_visual:
            _fgv = llm_force_generate_visual_on if sandbox_enabled else llm_force_generate_visual_off
            _invoked_llm = _fgv or llm_with_tools
        elif force_reddit:
            _fr = None
            if _reddit_resolved_comments_url and _incoming_looks_like_reddit_post_url(
                _reddit_resolved_comments_url
            ):
                _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
            elif _incoming_has_reddit_share_path(incoming_for_reddit):
                # Enlace /s/ sin URL canónica resuelta: forzar reddit_get_post; el parche posterior
                # sustituye por reddit_search_reddit(query=r/<sub> shortlink <slug>). Forzar search
                # directo empujaba query=URL y el MCP fallaba (evidencia: children undefined).
                _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
            elif _incoming_looks_like_reddit_post_url(incoming_for_reddit):
                _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
            if _fr is None:
                _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
            if _fr is None:
                _fr = llm_force_reddit_fallback_on if sandbox_enabled else llm_force_reddit_fallback_off
            _invoked_llm = _fr or llm_with_tools
        elif force_fetch_market_data:
            _ffmd = llm_force_fetch_market_on if sandbox_enabled else llm_force_fetch_market_off
            _invoked_llm = _ffmd or llm_with_tools
        elif force_run_sandbox:
            _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
            _invoked_llm = _frs or llm_with_tools
        if forced_name == "auto":
            _bind_base_identity = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
            _auto_tools = list(_bind_base_identity)
            _auto_before = [str(getattr(t, "name", "") or "") for t in _auto_tools]
            _auto_tools = without_privileged_mutation_tools(_auto_tools)
            _hide_sandbox = should_hide_sandbox_tools(incoming, _intent_incoming)
            if _hide_sandbox:
                _auto_tools = without_sandbox_tools(_auto_tools)
            _hide_storage_identity = should_hide_storage_identity_tools(
                incoming,
                _intent_incoming,
                explicit_storage_request=explicit_duckdb_schema_request,
            )
            if _hide_storage_identity:
                _auto_tools = without_storage_identity_tools(_auto_tools)
            if _reddit_share_mcp_exhausted:
                _auto_tools = [
                    t
                    for t in _auto_tools
                    if not str(getattr(t, "name", "") or "").startswith("reddit_")
                ]
            if _rag_turn_without_db_intent:
                _auto_tools = without_storage_tools(_auto_tools)
            if len(_auto_tools) < len(_bind_base_identity):
                _invoked_llm = _bind_tools(llm, _auto_tools)
        _llm_invoke_exc: BaseException | None = None
        try:
            _raise_if_chat_cancelled_from_state(state)
            from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

            resp = invoke_chat_model_with_transient_retries(_invoked_llm, _groq_msgs)
            if (
                is_market_analysis_worker
                and resp is not None
                and getattr(resp, "tool_calls", None)
            ):
                _ru_share = _first_reddit_url_in_text(incoming_for_reddit)
                if (
                    _ru_share
                    and _incoming_has_reddit_share_path(_ru_share)
                    and not _reddit_resolved_comments_url
                ):
                    resp = _patch_ai_reddit_share_tool_calls(
                        resp, _ru_share, attempt_index=reddit_search_tool_count
                    )
                elif _reddit_resolved_comments_url:
                    resp = _patch_reddit_get_post_args_from_canonical_url(
                        resp, _reddit_resolved_comments_url
                    )
        except Exception as exc:
            from duckclaw.graphs.chat_cancel import ChatCancelledError

            if isinstance(exc, ChatCancelledError):
                raise
            _llm_invoke_exc = exc
            _log.warning("[%s] LLM invoke failed in agent_node: %s", _wl, exc, exc_info=True)
            from duckclaw.integrations.llm_providers import failure_provider_label_for_llm_invoke

            _pl_fail = failure_provider_label_for_llm_invoke(_invoked_llm, provider)
            resp = AIMessage(content=_agent_node_llm_failure_user_message(exc, provider=_pl_fail))
        tool_calls = getattr(resp, "tool_calls", None) or []
        _is_goals_tick = (
            str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
            and proactive_review_event_phrase_in_text(str(incoming or ""))
        )
        if tool_calls:
            _tc_names: list[Any] = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    _tc_names.append(tc.get("name"))
                else:
                    _tc_names.append(getattr(tc, "name", None))
            _log.info("[%s] LLM tool_calls=%s", _wl, _tc_names)
        _resp_content = ""
        try:
            from duckclaw.integrations.llm_providers import lc_message_content_to_text

            _resp_content = (lc_message_content_to_text(resp) or "").strip()
        except Exception:
            _resp_content = str(getattr(resp, "content", "") or "").strip()
        _lh_gct_fix = _last_human_message_index(state.get("messages") or [])
        _post_tools_synthesis = _post_tools_synthesis_needed(
            state.get("messages") or [],
            incoming,
            last_human_idx=_lh_gct_fix,
            already_has_tool_result=already_has_tool_result,
        )
        _json_echo = _reply_is_tool_json_echo(_resp_content)
        _gct_lone_url_skip = _clock_only_lone_url_no_repair(
            incoming,
            state.get("messages") or [],
            last_human_idx=_lh_gct_fix,
        )
        _inline_repair_gate = _post_tools_synthesis or (
            _json_echo and not _gct_lone_url_skip
        )
        _inline_will_synth = bool(
            not tool_calls
            and _llm_invoke_exc is None
            and is_market_analysis_worker
            and _inline_repair_gate
            and (not _resp_content or _json_echo)
        )
        _market_inline_synth_attempted = False
        if (
            not tool_calls
            and _llm_invoke_exc is None
            and is_market_analysis_worker
            and _inline_repair_gate
            and (
                not _resp_content
                or _reply_is_tool_json_echo(_resp_content)
            )
        ):
            _market_inline_synth_attempted = True
            _gct_data = (
                _parse_get_current_time_json(_resp_content)
                or _latest_tool_json_since(
                    state.get("messages") or [], _lh_gct_fix, "get_current_time"
                )
                or {}
            )
            _day = str(_gct_data.get("day_of_week") or "")
            _tm = str(_gct_data.get("time") or "")[:5]
            _clock_hint = f"{_day} {_tm} COT".strip() if (_day or _tm) else ""
            _brand = (getattr(spec, "name", None) or _lid or "Worker").strip()
            _tools_ran = [
                str(getattr(m, "name", "") or "")
                for m in (state.get("messages") or [])[max(0, _lh_gct_fix + 1) :]
                if isinstance(m, ToolMessage)
            ]
            _tools_hint = ", ".join(dict.fromkeys(_tools_ran)) if _tools_ran else "herramientas"
            _follow_sys = SystemMessage(
                content=(
                    f"Ya ejecutaste {_tools_hint} en este turno. "
                    + (f"Encabezado {_brand} con {_clock_hint}. " if _clock_hint else "")
                    + "Redacta la respuesta final completa en español integrando el contexto visual "
                    "y los resultados de herramientas. PROHIBIDO pegar JSON crudo de herramientas."
                )
            )
            try:
                # Síntesis en prosa: sin bind_tools (evita re-forzar run_sandbox cuando el
                # follow-up SystemMessage queda como último mensaje del batch).
                resp = invoke_chat_model_with_transient_retries(
                    llm, list(_groq_msgs) + [_follow_sys]
                )
                try:
                    from duckclaw.integrations.llm_providers import lc_message_content_to_text

                    _resp_content = (lc_message_content_to_text(resp) or "").strip()
                except Exception:
                    _resp_content = str(getattr(resp, "content", "") or "").strip()
                tool_calls = getattr(resp, "tool_calls", None) or []
            except Exception as exc:
                _log.warning("[%s] post-tools synthesis retry failed: %s", _wl, exc)
        out = {**state, "messages": state["messages"] + [resp]}
        if _market_inline_synth_attempted:
            out["market_inline_synthesis_attempted"] = True
        if _llm_invoke_exc is not None:
            from duckclaw.integrations.llm_providers import is_transient_inference_connection_error

            out["_duckclaw_worker_llm_invoke_failed"] = True
            out["_duckclaw_worker_llm_transient"] = bool(
                is_transient_inference_connection_error(_llm_invoke_exc)
            )
            out["_duckclaw_worker_llm_failure_kind"] = type(_llm_invoke_exc).__name__
        else:
            for _k in (
                "_duckclaw_worker_llm_invoke_failed",
                "_duckclaw_worker_llm_transient",
                "_duckclaw_worker_llm_failure_kind",
            ):
                out.pop(_k, None)
        out.update(_identity_fields(state))
        return out
    return agent_node
