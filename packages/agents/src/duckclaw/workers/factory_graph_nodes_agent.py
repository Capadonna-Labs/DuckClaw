"""Agent node factory."""

from __future__ import annotations

from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.factory_agent_node_helpers import _identity_fields
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_graph_nodes_agent_invoke import make_agent_invoke_node
from langchain_core.messages import AIMessage


def make_agent_node(ctx: WorkerGraphContext):
    if ctx.llm is None:
        def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            out = {
                **state,
                "messages": state["messages"] + [AIMessage(content="Sin LLM configurado. Configura DUCKCLAW_LLM_PROVIDER.")],
            }
            out.update(_identity_fields(state))
            return out
        return agent_node
    return make_agent_invoke_node(ctx)
