"""Tool-round cap handling for set_reply (worker LangGraph)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from duckclaw.workers.factory_agent_node_helpers import (
    _last_human_message_index,
    _spec_logical_worker_id,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext

TOOL_CAP_EXHAUSTED_REPLY = (
    "Alcancé el límite de pasos con herramientas en este turno. "
    "Te resumo con lo ejecutado hasta ahora; si necesitas más, envía otra consulta."
)


def maybe_reply_for_tool_cap_exhausted(
    state: dict,
    ctx: WorkerGraphContext,
    msgs: list[Any],
    incoming: str,
    spec: Any,
) -> tuple[str | None, list[Any] | None]:
    """Cuando ``should_continue`` corta en max_tool_rounds con tool_calls pendientes."""
    max_rounds = max(1, int(ctx.max_tool_rounds))
    if int(state.get("_tool_round") or 0) < max_rounds:
        return None, None
    if not msgs:
        return None, None
    last = msgs[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return None, None

    spec_lid = _spec_logical_worker_id(spec)
    lh = _last_human_message_index(list(msgs))
    _ = lh, spec_lid, incoming  # síntesis NL en set_reply vía repair_tool_response_egress_reply
    reply = TOOL_CAP_EXHAUSTED_REPLY

    stripped_msgs: list[Any] | None = None
    if isinstance(last, AIMessage):
        stripped_msgs = list(msgs[:-1]) + [AIMessage(content=reply)]
    return reply, stripped_msgs
