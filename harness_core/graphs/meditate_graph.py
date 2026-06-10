"""LangGraph meditate thermostat: telemetry → distance → plan → dispatch."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from langgraph.graph import END, StateGraph

from harness_core.policies.corrective_allowlist import normalize_corrective_action, parse_corrective_actions_json
from harness_core.skills.emit_correction_delta import (
    emit_meditate_audit,
    emit_purge_stale_tasks,
    emit_quarantine_memory,
    set_circuit_breaker_pause,
)
from harness_core.skills.fetch_system_telemetry import fetch_system_telemetry
from harness_core.skills.notify_admin_alert import notify_admin_alert
from harness_core.skills.strix_compute_delta import strix_compute_delta
from harness_core.states.meditate_state import CorrectiveAction, HomeostasisTarget, MeditateState

_log = logging.getLogger(__name__)

_CIRCUIT_BREAKER_ERROR_RATE = 50.0


def _targets_from_state(state: MeditateState) -> HomeostasisTarget:
    raw = state.get("targets") or {}
    return HomeostasisTarget.model_validate(raw)


def _plan_rules(distance: dict[str, float], metrics: dict[str, Any]) -> list[CorrectiveAction]:
    """Hardcoded corrective rules from spec (deterministic baseline)."""
    actions: list[CorrectiveAction] = []
    err = float(metrics.get("error_rate_pct") or 0)
    if err > _CIRCUIT_BREAKER_ERROR_RATE:
        actions.append(
            CorrectiveAction(
                action_type="circuit_breaker_pause",
                requires_hitl=True,
                reason=f"error_rate_pct={err:.1f} exceeds {_CIRCUIT_BREAKER_ERROR_RATE}%",
            )
        )
        actions.append(
            CorrectiveAction(
                action_type="alert_admin",
                requires_hitl=True,
                reason="circuit breaker threshold breached",
            )
        )
    if float(distance.get("stale_tasks_count") or 0) > 0:
        actions.append(
            CorrectiveAction(
                action_type="purge_stale_tasks",
                requires_hitl=False,
                reason="stale tasks detected",
            )
        )
    if float(distance.get("memory_fragmentation_index") or 0) > 0:
        actions.append(
            CorrectiveAction(
                action_type="quarantine_corrupted_memory",
                requires_hitl=False,
                reason="pending embeddings exceed target fragmentation",
            )
        )
        actions.append(
            CorrectiveAction(
                action_type="request_compaction",
                requires_hitl=True,
                reason="memory fragmentation proxy above target",
            )
        )
    if float(distance.get("db_lock_events") or 0) > 0:
        actions.append(
            CorrectiveAction(
                action_type="alert_admin",
                requires_hitl=True,
                reason="DuckDB lock events during telemetry sweep",
            )
        )
    if float(distance.get("error_rate_pct") or 0) > 0 and err <= _CIRCUIT_BREAKER_ERROR_RATE:
        actions.append(
            CorrectiveAction(
                action_type="alert_admin",
                requires_hitl=True,
                reason="elevated error rate",
            )
        )
    if not actions:
        actions.append(CorrectiveAction(action_type="noop", requires_hitl=False, reason="within homeostasis"))
    return [normalize_corrective_action(a) for a in actions]


def _invoke_plan_llm(
    llm: Any,
    *,
    distance: dict[str, float],
    metrics: dict[str, Any],
    targets: HomeostasisTarget,
) -> list[CorrectiveAction]:
    from langchain_core.messages import HumanMessage, SystemMessage

    sys = SystemMessage(
        content=(
            "You are the meditate infrastructure planner. Respond ONLY with a JSON array of corrective actions. "
            "Each object must have: action_type (purge_stale_tasks|quarantine_corrupted_memory|request_compaction|"
            "alert_admin|circuit_breaker_pause|noop), requires_hitl (bool), reason (string), params (object). "
            "Rules: stale→purge_stale_tasks; fragmentation→quarantine_corrupted_memory + request_compaction; "
            "locks→alert_admin; error_rate_pct>50→circuit_breaker_pause + alert_admin."
        )
    )
    human = HumanMessage(
        content=json.dumps(
            {
                "distance_vector": distance,
                "current_metrics": metrics,
                "targets": targets.model_dump(),
            },
            ensure_ascii=False,
        )
    )
    resp = llm.invoke([sys, human])
    content = (getattr(resp, "content", None) or "").strip()
    try:
        return parse_corrective_actions_json(content, strict=True)
    except ValueError:
        retry_msg = HumanMessage(
            content="Format invalid. Respond ONLY with a JSON array of corrective action objects."
        )
        resp2 = llm.invoke([sys, human, retry_msg])
        content2 = (getattr(resp2, "content", None) or "").strip()
        return parse_corrective_actions_json(content2)


def node_sweep_telemetry(state: MeditateState) -> MeditateState:
    out: MeditateState = {**state, "status": "sweeping"}
    vault = (state.get("vault_db_path") or "").strip()
    if not vault:
        return {**out, "status": "failed", "error": "vault_db_path missing"}
    try:
        metrics, stale_ids, memory_ids, lock_events = fetch_system_telemetry(
            vault,
            tenant_id=str(state.get("tenant_id") or "default"),
            delta_interval_seconds=int(state.get("delta_interval_seconds") or 14400),
            targets=_targets_from_state(state),
        )
        if lock_events:
            m = metrics.model_copy(update={"db_lock_events": lock_events})
        else:
            m = metrics
        return {
            **out,
            "current_metrics": m.model_dump(),
            "stale_task_ids": stale_ids,
            "memory_ids_to_quarantine": memory_ids,
        }
    except Exception as exc:
        _log.debug("node_sweep_telemetry failed: %s", exc)
        return {**out, "status": "failed", "error": str(exc)}


def node_calculate_distance(state: MeditateState) -> MeditateState:
    out: MeditateState = {**state, "status": "calculating"}
    if state.get("status") == "failed":
        return out
    metrics = state.get("current_metrics") or {}
    try:
        distance = strix_compute_delta(metrics, _targets_from_state(state), use_sandbox=False)
        return {**out, "distance_vector": distance}
    except Exception as exc:
        return {**out, "status": "failed", "error": f"strix_compute_delta: {exc}"}


def node_plan_correction(state: MeditateState, *, llm: Any | None = None) -> MeditateState:
    out: MeditateState = {**state, "status": "planning"}
    if state.get("status") == "failed":
        return out
    distance = state.get("distance_vector") or {}
    metrics = state.get("current_metrics") or {}
    targets = _targets_from_state(state)
    try:
        if llm is not None:
            actions = _invoke_plan_llm(llm, distance=distance, metrics=metrics, targets=targets)
        else:
            actions = _plan_rules(distance, metrics)
        return {**out, "planned_actions": [a.model_dump() for a in actions]}
    except Exception as exc:
        noop = CorrectiveAction(action_type="noop", requires_hitl=False, reason=str(exc))
        return {**out, "planned_actions": [noop.model_dump()]}


def node_dispatch_actions(state: MeditateState) -> MeditateState:
    out: MeditateState = {**state, "status": "dispatching"}
    if state.get("status") == "failed":
        return {**out, "status": "failed"}

    tenant_id = str(state.get("tenant_id") or "default")
    worker_id = str(state.get("worker_id") or "")
    user_id = str(state.get("user_id") or "default")
    vault = str(state.get("vault_db_path") or "")
    admin_chat = str(state.get("admin_chat_id") or state.get("chat_id") or "")
    run_id = str(state.get("run_id") or uuid.uuid4())
    distance = state.get("distance_vector") or {}
    planned = state.get("planned_actions") or []
    stale_ids = list(state.get("stale_task_ids") or [])
    memory_ids = list(state.get("memory_ids_to_quarantine") or [])

    dispatched: list[dict[str, Any]] = []
    for raw in planned:
        try:
            action = normalize_corrective_action(raw)
        except Exception as exc:
            action = CorrectiveAction(action_type="noop", requires_hitl=False, reason=str(exc))

        entry = action.model_dump()
        entry["executed"] = False

        if action.action_type == "noop":
            entry["executed"] = True
            dispatched.append(entry)
            continue

        if action.requires_hitl and action.action_type in (
            "request_compaction",
            "alert_admin",
            "circuit_breaker_pause",
        ):
            notify_admin_alert(
                admin_chat,
                f"meditate HITL: {action.action_type} — {action.reason}",
                worker_id=worker_id,
                tenant_id=tenant_id,
                distance_vector=distance,
                actions=[entry],
            )
            if action.action_type == "circuit_breaker_pause":
                set_circuit_breaker_pause(tenant_id, worker_id, reason=action.reason)
            entry["executed"] = True
            dispatched.append(entry)
            continue

        if action.action_type == "purge_stale_tasks":
            ok = emit_purge_stale_tasks(
                tenant_id=tenant_id,
                user_id=user_id,
                target_db_path=vault,
                task_ids=stale_ids,
            )
            entry["executed"] = ok
            dispatched.append(entry)
            continue

        if action.action_type == "quarantine_corrupted_memory":
            ok = emit_quarantine_memory(
                tenant_id=tenant_id,
                user_id=user_id,
                target_db_path=vault,
                memory_ids=memory_ids,
            )
            entry["executed"] = ok
            dispatched.append(entry)
            continue

        dispatched.append(entry)

    final_status = "completed" if state.get("status") != "failed" else "failed"
    emit_meditate_audit(
        tenant_id=tenant_id,
        user_id=user_id,
        target_db_path=vault,
        run_id=run_id,
        distance_vector=distance,
        actions_json=dispatched,
        status=final_status,
    )
    return {**out, "status": final_status, "dispatched_actions": dispatched, "run_id": run_id}


def build_meditate_graph(*, llm: Any | None = None) -> StateGraph:
    """Build meditate graph; optional llm enables structured plan_correction."""
    builder = StateGraph(MeditateState)
    builder.add_node("sweep_telemetry", node_sweep_telemetry)
    builder.add_node("calculate_distance", node_calculate_distance)

    if llm is not None:
        def _plan(state: MeditateState) -> MeditateState:
            return node_plan_correction(state, llm=llm)

        builder.add_node("plan_correction", _plan)
    else:
        builder.add_node("plan_correction", node_plan_correction)

    builder.add_node("dispatch_actions", node_dispatch_actions)
    builder.set_entry_point("sweep_telemetry")
    builder.add_edge("sweep_telemetry", "calculate_distance")
    builder.add_edge("calculate_distance", "plan_correction")
    builder.add_edge("plan_correction", "dispatch_actions")
    builder.add_edge("dispatch_actions", END)
    return builder


def invoke_meditate_run(initial: MeditateState, *, llm: Any | None = None) -> MeditateState:
    """Compile and invoke meditate graph with run_id default."""
    state: MeditateState = {
        "run_id": str(uuid.uuid4()),
        "status": "pending",
        **initial,
    }
    graph = build_meditate_graph(llm=llm).compile()
    result = graph.invoke(state)
    if isinstance(result, dict):
        return result  # type: ignore[return-value]
    return state


meditate_graph = build_meditate_graph().compile()
