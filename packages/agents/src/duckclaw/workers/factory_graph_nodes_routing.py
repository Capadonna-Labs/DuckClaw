"""Routing nodes and conditional edge functions."""

from __future__ import annotations

from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.factory_graph_context import WorkerGraphContext


def make_should_continue(ctx: WorkerGraphContext):
    max_rounds = max(1, int(ctx.max_tool_rounds))

    def should_continue(state: dict) -> str:
        if int(state.get("_tool_round") or 0) >= max_rounds:
            return "end"
        last = state["messages"][-1]
        _has_tools = bool(getattr(last, "tool_calls", None))
        return "tools" if _has_tools else "end"

    return should_continue


def make_fact_check_node(ctx: WorkerGraphContext):
    llm = ctx.llm
    max_retries = ctx.context_guard_max_retries

    def fact_check_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import fact_checker_node as _fc
        return _fc(state, llm, max_retries=max_retries)

    return fact_check_node


def make_self_correction_node(ctx: WorkerGraphContext):
    llm = ctx.llm

    def self_correction_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import self_correction_node as _sc
        return _sc(state, llm)

    return self_correction_node


def make_handoff_reply_node(ctx: WorkerGraphContext):
    def handoff_reply_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import handoff_reply_node as _hr
        return _hr(state)

    return handoff_reply_node


def make_route_after_fact_check(ctx: WorkerGraphContext):
    def route_after_fact_check(state: dict) -> str:
        return state.get("context_guard_route", "approved")

    return route_after_fact_check


def make_route_after_set_reply(ctx: WorkerGraphContext):
    def route_after_set_reply(state: dict) -> str:
        return (
            "agent"
            if state.get("visual_evidence_graph_retry") or state.get("position_metrics_graph_retry")
            else "end"
        )

    return route_after_set_reply


def make_homeostasis_node(ctx: WorkerGraphContext):
    def homeostasis_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        """HomeostasisNode: Percepción-Sorpresa-Restauración-Actualización. Fase 1: pass-through (tabla ya creada en run_schema).
        IMPORTANTE: retornar state para preservar input/incoming; retornar {} vacío hace que LangGraph pierda el estado."""
        return state

    return homeostasis_node
