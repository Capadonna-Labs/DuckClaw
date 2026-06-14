"""Replan/resilience state helpers for the manager graph."""

from __future__ import annotations

from typing import Any

from duckclaw.graphs.agent_resilience import (
    format_replan_task_suffix,
    plan_max_attempts_from_env,
    replan_enabled,
)


def _initial_replan_state() -> dict[str, Any]:
    """Initial LangGraph state fields used by the manager replan loop."""
    return {
        "plan_attempt_index": 0,
        "plan_max_attempts": plan_max_attempts_from_env(),
        "plan_failure_reasons": [],
        "replan_requested": False,
    }


def _planned_task_with_replan_suffix(
    planned_task: str,
    plan_attempt_index: int,
    plan_max_attempts: int,
) -> str:
    """Append the retry directive only on replan attempts."""
    planned = (planned_task or "").strip()
    if replan_enabled() and plan_attempt_index > 0:
        return planned + format_replan_task_suffix(plan_attempt_index, plan_max_attempts)
    return planned


def _replan_output_fields(
    *,
    replan_after: bool,
    exhausted_final: bool,
    next_plan_attempt: int,
    max_attempts: int,
    failure_reasons: list[str],
) -> dict[str, Any]:
    """Final manager state fields that drive LangGraph routing after worker invocation."""
    if replan_after:
        return {
            "replan_requested": True,
            "plan_attempt_index": next_plan_attempt,
            "plan_failure_reasons": failure_reasons,
        }
    if exhausted_final:
        return {
            "replan_requested": False,
            "plan_attempt_index": max_attempts,
            "plan_failure_reasons": failure_reasons,
        }
    return {
        "replan_requested": False,
        "plan_attempt_index": 0,
        "plan_failure_reasons": [],
    }


__all__ = [
    "_initial_replan_state",
    "_planned_task_with_replan_suffix",
    "_replan_output_fields",
]
