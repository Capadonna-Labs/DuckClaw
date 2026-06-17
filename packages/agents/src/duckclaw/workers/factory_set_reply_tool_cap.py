"""Tool-round cap handling for set_reply (worker LangGraph)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from duckclaw.egress.tool_response_repair import (
    deterministic_tool_response_summary as _deterministic_tool_response_summary,
    reply_is_tool_json_echo as _reply_is_tool_json_echo,
)
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
    det = _deterministic_tool_response_summary(
        list(msgs),
        lh,
        spec_lid,
        incoming,
        worker_display_name=str(getattr(spec, "name", None) or ""),
    )
    reply = TOOL_CAP_EXHAUSTED_REPLY
    if (det or "").strip() and not _reply_is_tool_json_echo(det):
        reply = f"{det.strip()}\n\n{reply}"

    stripped_msgs: list[Any] | None = None
    if isinstance(last, AIMessage):
        stripped_msgs = list(msgs[:-1]) + [AIMessage(content=reply)]
    return reply, stripped_msgs
