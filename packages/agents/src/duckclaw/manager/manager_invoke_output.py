"""Build invoke-worker output payload (reply, replan fields, artifacts)."""

from __future__ import annotations

from typing import Any


def build_invoke_worker_output(
    *,
    exhausted_final: bool,
    reasons_acc: list[str],
    reply: str,
    assigned: str,
    plan_title: str | None,
    messages: Any,
    worker_invoke: Any,
    raw_worker_reply: str,
    state: dict[str, Any],
    max_a: int,
    replan_after: bool,
    next_plan_attempt: int,
) -> dict[str, Any]:
    from duckclaw.graphs.agent_resilience import format_exhausted_plan_failure
    from duckclaw.graphs.sandbox import extract_latest_sandbox_figure_base64
    from duckclaw.graphs.state import ManagerAgentState
    from duckclaw.manager.resilience_flow import _replan_output_fields

    if exhausted_final:
        reply = format_exhausted_plan_failure(reasons_acc)
    out: ManagerAgentState = {
        "reply": reply,
        "_audit_done": True,
        "assigned_worker_id": assigned,
        "plan_title": plan_title,
    }  # type: ignore[assignment]
    if messages is not None:
        out["messages"] = messages
    b64 = ""
    if isinstance(worker_invoke, dict):
        b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
    if not b64 and messages is not None:
        b64 = extract_latest_sandbox_figure_base64(messages) or ""
    if b64:
        out["sandbox_photo_base64"] = b64
    aid = ""
    if isinstance(worker_invoke, dict):
        aid = (worker_invoke.get("visual_artifact_id") or "").strip()
    if aid:
        out["visual_artifact_id"] = aid
    if "active_mission" in state:
        out["active_mission"] = state.get("active_mission")
    if "handoff_context" in state:
        out["handoff_context"] = state.get("handoff_context")
    out["last_worker_raw_reply"] = raw_worker_reply or reply
    out["plan_max_attempts"] = max_a
    out.update(
        _replan_output_fields(
            replan_after=replan_after,
            exhausted_final=exhausted_final,
            next_plan_attempt=next_plan_attempt,
            max_attempts=max_a,
            failure_reasons=reasons_acc,
        )
    )
    return out
