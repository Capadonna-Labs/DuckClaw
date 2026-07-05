"""Conditional edge routing for the manager graph."""

from __future__ import annotations

from duckclaw.graphs.state import ManagerAgentState
from duckclaw.manager.fast_replies import (
    _manager_capabilities_fast_path_ok,
    _manager_greeting_fast_path_ok,
    _manager_knowledge_inventory_fast_path_ok,
)
from duckclaw.manager.routing import _worker_matches_id
from duckclaw.utils.logger import get_obs_logger, log_sys

_obs = get_obs_logger()


def _fast_path_user_text(state: ManagerAgentState) -> str:
    return (
        state.get("user_incoming")
        or state.get("incoming")
        or state.get("input")
        or state.get("message")
        or ""
    ).strip()


def route_after_plan(state: ManagerAgentState) -> str:
    mspec = state.get("mercenary_spec")
    if isinstance(mspec, dict) and str(mspec.get("directive") or "").strip():
        return "mercenary"
    return "invoke_worker"


def route_after_invoke_worker(state: ManagerAgentState) -> str:
    current_worker = (state.get("assigned_worker_id") or "").strip()
    if state.get("replan_requested"):
        log_sys(_obs, "manager route: replan -> plan (reintento de planificación)")
        return "plan"
    mission = state.get("active_mission")
    if not isinstance(mission, dict):
        return "end"
    target_worker = (mission.get("target_worker") or "").strip()
    if not target_worker or not current_worker:
        return "end"
    if _worker_matches_id(current_worker, target_worker):
        source_w = (mission.get("source_worker") or "").strip()
        available = state.get("available_templates") or []
        if source_w and not any(_worker_matches_id(wid, source_w) for wid in available):
            return "end"
        return "return_to_source"
    return "end"


def route_after_router(state: ManagerAgentState) -> str:
    user_text = _fast_path_user_text(state)
    greeting_ok = _manager_greeting_fast_path_ok(user_text)
    capabilities_ok = _manager_capabilities_fast_path_ok(user_text)
    knowledge_ok = _manager_knowledge_inventory_fast_path_ok(user_text)
    if greeting_ok or capabilities_ok or knowledge_ok:
        return "greeting_shortcut"
    return "plan"


__all__ = ["route_after_invoke_worker", "route_after_plan", "route_after_router"]
