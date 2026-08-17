"""Position metrics egress retry must re-enter agent (same as visual evidence)."""

from __future__ import annotations

from duckclaw.egress.evidence_validator import (
    enforce_position_metrics_evidence_rule,
    position_metrics_retry_system_message,
)
from duckclaw.position_metrics import POSITION_METRICS_RETRY_REASON
from duckclaw.workers.factory_graph_nodes_routing import make_route_after_set_reply
from duckclaw.workers.factory_graph_context import WorkerGraphContext


class _Spec:
    skills_list = ["position_metrics"]


def _route(state: dict) -> str:
    route_fn = make_route_after_set_reply(WorkerGraphContext(worker_id="t", db=None, spec=_Spec()))
    return route_fn(state)


def test_position_metrics_retry_routes_back_to_agent() -> None:
    reply = "Distancia a SL: 5.2% · TP a 3.1% · RR 1.5"
    _, reason = enforce_position_metrics_evidence_rule(
        reply=reply,
        messages=[],
        spec=_Spec(),
    )
    assert reason == POSITION_METRICS_RETRY_REASON

    next_state = {
        "messages": [position_metrics_retry_system_message()],
        "position_metrics_retry_count": 1,
        "position_metrics_graph_retry": True,
        "reply": "",
        "internal_reply": "",
    }
    route = _route(next_state)
    assert route == "agent", (
        "position_metrics retry must loop to agent; got end → Sin respuesta."
    )
