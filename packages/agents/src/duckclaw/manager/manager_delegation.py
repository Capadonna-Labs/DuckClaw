"""Orchestrator delegate resolution for coordinator workers."""

from __future__ import annotations

from typing import Any

from duckclaw.manager.manager_planner_llm import _llm_plan_from_model

_PLANNER_FALLBACK = (
    "Elige delegate_worker_id de la lista permitida y redacta tasks concisas "
    "para el subagente elegido."
)


def _load_orchestrator_planner_prompt(coordinator_id: str, templates_root: Any) -> str:
    from duckclaw.workers.manifest import get_worker_dir

    path = get_worker_dir(coordinator_id, templates_root) / "orchestrator_planner.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return _PLANNER_FALLBACK


def _resolve_orchestrator_delegate(
    incoming: str,
    pool: list[str],
    coordinator_id: str,
    llm: Any | None,
    planner_system_prompt: str,
    templates_root: Any,
) -> str:
    from duckclaw.workers.orchestrator import pick_delegate_from_planner, pick_delegate_heuristic

    delegate: str | None = None
    if llm is not None:
        orch_prompt = _load_orchestrator_planner_prompt(coordinator_id, templates_root)
        combined = (planner_system_prompt or "").strip()
        if combined:
            combined = f"{combined}\n\n{orch_prompt}"
        else:
            combined = orch_prompt
        parsed = _llm_plan_from_model(
            llm, incoming, combined, orchestrator_pool=list(pool) + [coordinator_id]
        )
        if parsed:
            _, _, _, delegate_id = parsed
            delegate = pick_delegate_from_planner(delegate_id, list(pool) + [coordinator_id], templates_root)
    if not delegate:
        delegate = pick_delegate_heuristic(incoming, list(pool) + [coordinator_id], coordinator_id=coordinator_id)
    return delegate or coordinator_id


__all__ = ["_load_orchestrator_planner_prompt", "_resolve_orchestrator_delegate"]
