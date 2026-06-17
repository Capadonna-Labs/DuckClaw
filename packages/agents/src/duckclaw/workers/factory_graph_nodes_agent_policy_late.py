"""Agent late.py phase."""

from __future__ import annotations

from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.runtime_policy_helpers import (
    worker_has_runtime_capability as _worker_has_runtime_capability,
    worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool,
)
from duckclaw.workers.tool_invocation_policy import decide_market_data_tool_invocation as _decide_market_data_tool_invocation
from langchain_core.messages import AIMessage

from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_agent_shared import AGENT_CTX_UNPACK


def make_agent_policy_late(ctx: WorkerGraphContext):
    exec(AGENT_CTX_UNPACK, {"ctx": ctx}, locals())
    def run(state: dict, config: Optional[RunnableConfig] = None) -> dict | None:
                _intent_incoming = ctx.agent_turn['_intent_incoming']
                _orch = ctx.agent_turn['_orch']
                _reddit_resolved_comments_url = ctx.agent_turn['_reddit_resolved_comments_url']
                _reddit_share_mcp_exhausted = ctx.agent_turn['_reddit_share_mcp_exhausted']
                _visual_tool_already_ok = ctx.agent_turn['_visual_tool_already_ok']
                _wl = ctx.agent_turn['_wl']
                already_has_tool_result = ctx.agent_turn['already_has_tool_result']
                force_admin_sql = ctx.agent_turn['force_admin_sql']
                force_read_sql = ctx.agent_turn['force_read_sql']
                force_reddit = ctx.agent_turn['force_reddit']
                force_schema = ctx.agent_turn['force_schema']
                force_tavily = ctx.agent_turn['force_tavily']
                force_visual = ctx.agent_turn['force_visual']
                incoming = ctx.agent_turn['incoming']
                incoming_for_reddit = ctx.agent_turn['incoming_for_reddit']
                is_latest_game = ctx.agent_turn['is_latest_game']
                is_schema = ctx.agent_turn['is_schema']
                is_table_content = ctx.agent_turn['is_table_content']
                reddit_search_tool_count = ctx.agent_turn['reddit_search_tool_count']
                state = ctx.agent_turn['state']
                summarize_stored_directive = ctx.agent_turn['summarize_stored_directive']
                telegram_context_summarize_directive = ctx.agent_turn['telegram_context_summarize_directive']
                market_data_tool_decision = _decide_market_data_tool_invocation(
                    spec=spec,
                    incoming=incoming,
                    available_tools=tools_by_name,
                    already_has_tool_result=already_has_tool_result,
                    summarize_ok_for_forced_ohlcv=not telegram_context_summarize_directive,
                    blocked_by_prior_decision=bool(
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                        or force_reddit
                    ),
                    heuristic_first_tool_enabled=_worker_use_heuristic_first_tool(spec),
                )
                force_fetch_market_data = market_data_tool_decision.is_tool("fetch_market_data")

                _incoming_l = (incoming or "").lower()
                _is_graph_request = any(
                    k in _incoming_l
                    for k in (
                        "gráfica",
                        "grafica",
                        "gráfico",
                        "grafico",
                        "diagrama",
                        "plot",
                        "streamplot",
                        "subplot",
                        "matplotlib",
                        "seaborn",
                        "plotly",
                    )
                )
                _is_plot_docs_request = any(
                    k in _incoming_l
                    for k in (
                        "matplotlib.org",
                        "seaborn.pydata.org",
                        "plotly.com/python",
                        "docs matplotlib",
                        "doc matplotlib",
                        "docs seaborn",
                        "doc seaborn",
                        "docs plotly",
                        "doc plotly",
                    )
                )
                _plot_capable_worker = _worker_has_runtime_capability(spec, "plot_docs_lookup")
                force_plot_docs = bool(
                    has_tavily
                    and _plot_capable_worker
                    and _is_plot_docs_request
                    and not telegram_context_summarize_directive
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_reddit
                        or force_fetch_market_data
                    )
                    and not already_has_tool_result
                )
                force_run_sandbox = bool(
                    has_run_sandbox
                    and _plot_capable_worker
                    and _is_graph_request
                    and not telegram_context_summarize_directive
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                        or force_plot_docs
                        or force_reddit
                        or force_fetch_market_data
                    )
                    and not already_has_tool_result
                )
                if not _worker_use_heuristic_first_tool(spec):
                    force_plot_docs = False
                    force_run_sandbox = False
                if force_plot_docs:
                    force_tavily = True

                _lh_current_time = _last_human_message_index(state.get("messages") or [])
                _called_time_tools = (
                    {"get_current_time"}
                    if _tool_called_since(
                        state.get("messages") or [], _lh_current_time, "get_current_time"
                    )
                    else set()
                )
                current_time_tool_decision = _decide_current_time_tool_invocation(
                    spec=spec,
                    incoming=incoming,
                    available_tools=tools_by_name,
                    called_tools_since_last_human=_called_time_tools,
                    already_has_tool_result=already_has_tool_result,
                    summarize_directive=telegram_context_summarize_directive,
                    orchestration_active=bool(_orch),
                )
                if current_time_tool_decision.direct_tool_call and current_time_tool_decision.tool_name:
                    _forced_tid_current_time = f"call_policy_{current_time_tool_decision.tool_name}_{int(time.time() * 1000)}"
                    _forced_tc_current_time = [
                        {
                            "name": current_time_tool_decision.tool_name,
                            "args": dict(current_time_tool_decision.tool_args),
                            "id": _forced_tid_current_time,
                            "type": "tool_call",
                        }
                    ]
                    _log.info(
                        "[%s] runtime policy → %s reason=%s",
                        _wl,
                        current_time_tool_decision.tool_name,
                        current_time_tool_decision.reason,
                    )
                    _out_current_time = {
                        **state,
                        "messages": state["messages"] + [AIMessage(content="", tool_calls=_forced_tc_current_time)],
                    }
                    _out_current_time.update(_identity_fields(state))
                    return _out_current_time

                sandbox_enabled = _sandbox_enabled_for_state(state)

                _force_vlm_evidence_retry = bool(
                    int(state.get("visual_evidence_retry_count") or 0) > 0
                    and is_market_analysis_worker
                    and has_read_sql
                    and _worker_use_heuristic_first_tool(spec)
                    and not telegram_context_summarize_directive
                    and not summarize_stored_directive
                    and not already_has_tool_result
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_tavily
                        or force_reddit
                        or force_fetch_market_data
                        or force_plot_docs
                        or force_run_sandbox
                    )
                )
                if _force_vlm_evidence_retry:
                    force_read_sql = True
                _reddit_http_prefetch_ctx: Optional[str] = None

                if (
                    force_visual
                    and has_generate_visual
                    and not already_has_tool_result
                    and not _visual_tool_already_ok
                ):
                    _vis_prompt = (incoming or "").strip()[:1200]
                    _forced_tid = f"call_generate_visual_{int(time.time() * 1000)}"
                    _forced_tc = [
                        {
                            "name": "generate_visual_asset",
                            "args": {
                                "prompt": _vis_prompt,
                                "negative_prompt": "",
                                "aspect_ratio": "1:1",
                            },
                            "id": _forced_tid,
                            "type": "tool_call",
                        }
                    ]
                    _log.info(
                        "[%s] runtime policy visual → generate_visual_asset prompt=%r",
                        _wl,
                        _vis_prompt[:120],
                    )
                    _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                    _out_vis = {**state, "messages": state["messages"] + [_forced_resp]}
                    _out_vis.update(_identity_fields(state))
                    return _out_vis

                ctx.agent_turn.update({'force_fetch_market_data': force_fetch_market_data, 'force_read_sql': force_read_sql, 'force_run_sandbox': force_run_sandbox, 'force_tavily': force_tavily, 'sandbox_enabled': sandbox_enabled})
                return None

    return run
