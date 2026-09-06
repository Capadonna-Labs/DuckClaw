"""Agent node LLM invoke tail."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.factory_agent_node_helpers import (
    _agent_node_llm_failure_user_message,
    _identity_fields,
    _last_human_message_index,
    _raise_if_chat_cancelled_from_state,
    _worker_log_label,
)
from duckclaw.forge.rag.prompt_policy import (
    playground_document_turn_system_prompt,
    rag_turn_system_prompt,
)
from duckclaw.forge.rag.tool_policy import (
    should_prioritize_documents_over_storage_tools,
    should_prioritize_rag_over_storage_tools,
    without_storage_tools,
)
from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.workers.db_intent_policy import explicit_duckdb_storage_request
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_agent_policy_early import make_agent_policy_early
from duckclaw.workers.factory_graph_nodes_agent_policy_late import make_agent_policy_late
from duckclaw.workers.factory_graph_nodes_agent_shared import load_agent_env, unpack_agent_bindings
from duckclaw.workers.factory_reddit_helpers import _patch_reddit_get_post_args_from_canonical_url
from duckclaw.workers.provider_input_budget import apply_provider_input_budget as _apply_provider_input_budget
from duckclaw.workers.runtime_policy_helpers import worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool
from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs, log_pack_filter_result
from duckclaw.workers.tool_surface_policy import (
    should_hide_sandbox_tools,
    should_hide_storage_identity_tools,
    without_privileged_mutation_tools_for_auto_bind,
    without_sandbox_tools,
    without_storage_identity_tools,
)
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

_log = logging.getLogger(__name__)


def make_agent_invoke_node(ctx: WorkerGraphContext):
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
        force_read_sql = ctx.agent_turn['force_read_sql']
        force_orch_tool = ctx.agent_turn.get('force_orch_tool')
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
        _reddit_http_prefetch_ctx: str | None = None
        llm_with_tools = llm_with_tools_on if sandbox_enabled else llm_with_tools_off
        forced_name = "auto"
        if force_admin_sql:
            forced_name = "admin_sql"
        elif force_orch_tool:
            forced_name = force_orch_tool
        elif force_read_sql:
            forced_name = "read_sql"
        elif force_schema:
            forced_name = "inspect_schema"
        elif force_visual:
            forced_name = primary_visual_tool or "generate_visual_asset"
        elif force_tavily:
            forced_name = "tavily_search"
        elif force_reddit:
            forced_name = "reddit"
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
        from duckclaw.workers.reddit_formatters import sanitize_reddit_tool_messages_for_llm

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
                        "La imagen ya fue generada con una tool visual en este turno. "
                        "Responde al usuario con la ruta/artefacto; NO vuelvas a llamar "
                        "generate_visual_asset, generate_flux_image ni edit_visual_asset."
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
                    from duckclaw.workers.reddit_formatters import build_reddit_llm_context_block

                    _reddit_ctx_block = build_reddit_llm_context_block(str(_rm.content or ""))
                    break
        if _reddit_ctx_block:
            _msg_list = [SystemMessage(content=_reddit_ctx_block)] + _msg_list
        _rag_turn_without_db_intent = should_prioritize_rag_over_storage_tools(
            incoming,
            _intent_incoming,
            explicit_storage_request=explicit_duckdb_storage_request,
        )
        _document_turn_without_db_intent = should_prioritize_documents_over_storage_tools(
            incoming,
            _intent_incoming,
            explicit_storage_request=explicit_duckdb_storage_request,
        )
        if _document_turn_without_db_intent:
            _log.info("[%s] document attachment turn: storage tools hidden", _wl)
            _msg_list = [
                SystemMessage(content=playground_document_turn_system_prompt())
            ] + [m for m in _msg_list if not isinstance(m, SystemMessage)]
        elif _rag_turn_without_db_intent:
            _rag_tid = (state.get("tenant_id") or "default").strip() or "default"
            _msg_list = [
                SystemMessage(
                    content=rag_turn_system_prompt(
                        prompt_policies,
                        _lid,
                        tenant_id=_rag_tid,
                    )
                )
            ] + [m for m in _msg_list if not isinstance(m, SystemMessage)]
        _mlx_provider = (provider or "").strip().lower() in ("mlx", "iotcorelabs")
        _bind_est = (
            len(_tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind)
            if _mlx_provider
            else 0
        )
        _groq_msgs = _apply_provider_input_budget(
            _msg_list,
            provider=provider,
            bound_tools_n=_bind_est,
        )
        _invoked_llm: Any = llm_with_tools
        if force_admin_sql:
            _fa = llm_force_admin_sql_on if sandbox_enabled else llm_force_admin_sql_off
            _invoked_llm = _fa or llm_with_tools
        elif force_orch_tool:
            if force_orch_tool in ("execute_sandbox_script", "run_sandbox") and has_run_sandbox:
                _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
                _invoked_llm = _frs or llm_with_tools
            else:
                from duckclaw.workers.tool_binding import tool_choice_function as _tool_choice_function

                _orch_bind_tools = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
                _orch_llm_base = llm_with_tools_on if sandbox_enabled else llm_with_tools_off
                if force_orch_tool not in {
                    str(getattr(t, "name", "") or "") for t in _orch_bind_tools
                }:
                    _log.warning(
                        "[%s] force_orch_tool=%s not in bind surface; falling back to auto",
                        _wl,
                        force_orch_tool,
                    )
                    _invoked_llm = llm_with_tools
                else:
                    _invoked_llm = _bind_tools(
                        _orch_llm_base,
                        _orch_bind_tools,
                        tool_choice=_tool_choice_function(force_orch_tool),
                    )
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
        elif force_run_sandbox:
            _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
            _invoked_llm = _frs or llm_with_tools
        if forced_name == "auto":
            _bind_base_identity = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
            _auto_tools = list(_bind_base_identity)
            _auto_before = [str(getattr(t, "name", "") or "") for t in _auto_tools]
            _auto_tools = without_privileged_mutation_tools_for_auto_bind(
                _auto_tools,
                spec=spec,
            )
            _hide_sandbox = should_hide_sandbox_tools(incoming, _intent_incoming)
            if _hide_sandbox:
                _auto_tools = without_sandbox_tools(_auto_tools)
            _hide_storage_identity = should_hide_storage_identity_tools(
                incoming,
                _intent_incoming,
                explicit_storage_request=explicit_duckdb_storage_request,
            )
            if _hide_storage_identity:
                _auto_tools = without_storage_identity_tools(_auto_tools)
            if _reddit_share_mcp_exhausted:
                _auto_tools = [
                    t
                    for t in _auto_tools
                    if not str(getattr(t, "name", "") or "").startswith("reddit_")
                ]
            if _rag_turn_without_db_intent or _document_turn_without_db_intent:
                _auto_tools = without_storage_tools(_auto_tools)
            _pack_result = apply_runtime_tool_packs(
                _auto_tools,
                spec=spec,
                intent_text=_intent_incoming,
                messages=state.get("messages") or [],
            )
            _auto_tools = _pack_result.tools
            log_pack_filter_result(_wl, _pack_result)
            _auto_after = [str(getattr(t, "name", "") or "") for t in _auto_tools]
            if _auto_after != _auto_before:
                _invoked_llm = _bind_tools(llm, _auto_tools)
        if _mlx_provider:
            _bound_n = _bind_est
            try:
                _lk = getattr(_invoked_llm, "kwargs", None)
                if isinstance(_lk, dict) and _lk.get("tools"):
                    _bound_n = len(_lk.get("tools") or [])
            except Exception:
                pass
            _groq_msgs = _apply_provider_input_budget(
                _msg_list,
                provider=provider,
                bound_tools_n=_bound_n,
            )
        _llm_invoke_exc: BaseException | None = None
        try:
            _raise_if_chat_cancelled_from_state(state)
            from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

            resp = invoke_chat_model_with_transient_retries(_invoked_llm, _groq_msgs)
            if (
                has_reddit_tools
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
        if not tool_calls and _llm_invoke_exc is None and _mlx_provider and _resp_content:
            from duckclaw.integrations.llm_providers import extract_embedded_tool_invokes
            from uuid import uuid4

            _embedded = extract_embedded_tool_invokes(_resp_content)
            if _embedded:
                _synth_calls: list[dict[str, Any]] = []
                for _ename, _eparams in _embedded:
                    _synth_calls.append(
                        {
                            "id": f"call_{uuid4().hex[:12]}",
                            "name": _ename,
                            "args": _eparams if isinstance(_eparams, dict) else {},
                        }
                    )
                resp = AIMessage(content="", tool_calls=_synth_calls)
                tool_calls = _synth_calls
                _resp_content = ""
                _log.info(
                    "[%s] MLX JSON tool → synthesized tool_calls=%s",
                    _wl,
                    [tc.get("name") for tc in _synth_calls],
                )
        if (
            not tool_calls
            and _llm_invoke_exc is None
            and force_orch_tool
        ):
            from duckclaw.workers.sandbox_force_repair import (
                extract_python_from_llm_text,
                is_forced_sandbox_tool,
                resolve_orchestration_fallback_code,
                synthesize_sandbox_tool_call,
            )

            if is_forced_sandbox_tool(force_orch_tool):
                _sandbox_code = extract_python_from_llm_text(_resp_content)
                if not _sandbox_code:
                    _frs_repair = (
                        llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
                    )
                    if _frs_repair is not None:
                        _retry_sys = SystemMessage(
                            content=(
                                f"OBLIGATORIO: invoca únicamente `{force_orch_tool}` con "
                                "argumento `code` (script Python completo). "
                                "Prohibido responder en prosa sin tool_call."
                            )
                        )
                        try:
                            _retry_resp = invoke_chat_model_with_transient_retries(
                                _frs_repair,
                                list(_groq_msgs) + [_retry_sys],
                            )
                            _retry_calls = getattr(_retry_resp, "tool_calls", None) or []
                            if _retry_calls:
                                resp = _retry_resp
                                tool_calls = _retry_calls
                                try:
                                    _resp_content = (
                                        lc_message_content_to_text(resp) or ""
                                    ).strip()
                                except Exception:
                                    _resp_content = str(
                                        getattr(resp, "content", "") or ""
                                    ).strip()
                                _log.info(
                                    "[%s] sandbox force repair: retry tool_calls=%s",
                                    _wl,
                                    [
                                        tc.get("name")
                                        if isinstance(tc, dict)
                                        else getattr(tc, "name", None)
                                        for tc in _retry_calls
                                    ],
                                )
                        except Exception as _retry_exc:
                            _log.warning(
                                "[%s] sandbox force repair retry failed: %s",
                                _wl,
                                _retry_exc,
                            )
                _used_manifest_fallback = False
                if not tool_calls:
                    _fallback = resolve_orchestration_fallback_code(spec)
                    if _fallback:
                        _sandbox_code = _fallback
                        _used_manifest_fallback = True
                if not tool_calls and _sandbox_code:
                    _repair_tc = synthesize_sandbox_tool_call(
                        str(force_orch_tool),
                        _sandbox_code,
                    )
                    resp = AIMessage(content="", tool_calls=[_repair_tc])
                    tool_calls = [_repair_tc]
                    _resp_content = ""
                    _log.info(
                        "[%s] sandbox orchestration repair → synthesized %s",
                        _wl,
                        force_orch_tool,
                    )
            else:
                # ponytail: mirrors the sandbox repair above for any other manifest-forced
                # tool (e.g. publish_custom_report) — see orchestration_force_repair.py.
                from duckclaw.workers.orchestration_force_repair import retry_forced_tool_once

                _retry_resp, _retry_calls = retry_forced_tool_once(
                    _invoked_llm,
                    _groq_msgs,
                    str(force_orch_tool),
                    worker_log_label=_wl,
                    log=_log,
                )
                if _retry_calls:
                    resp = _retry_resp
                    tool_calls = _retry_calls
                    try:
                        _resp_content = (lc_message_content_to_text(resp) or "").strip()
                    except Exception:
                        _resp_content = str(getattr(resp, "content", "") or "").strip()
        out = {**state, "messages": state["messages"] + [resp]}
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
