"""Compute infrastructure homeostasis deltas for meditate.

Positive values mean the observed metric exceeds its target and needs attention.
Zero or negative values are aligned.
"""

from __future__ import annotations

from typing import Any

from harness_core.states.loop_state import CurrentMetrics, HomeostasisTarget


def _as_metrics(metrics: CurrentMetrics | dict[str, Any]) -> CurrentMetrics:
    if isinstance(metrics, CurrentMetrics):
        return metrics
    return CurrentMetrics.model_validate(metrics or {})


def _as_targets(targets: HomeostasisTarget | dict[str, Any]) -> HomeostasisTarget:
    if isinstance(targets, HomeostasisTarget):
        return targets
    return HomeostasisTarget.model_validate(targets or {})


def compute_distance_vector(
    metrics: CurrentMetrics | dict[str, Any],
    targets: HomeostasisTarget | dict[str, Any],
) -> dict[str, float]:
    observed = _as_metrics(metrics)
    target = _as_targets(targets)
    return {
        "error_rate_pct": float(observed.error_rate_pct) - float(target.error_rate_pct),
        "stale_tasks_count": float(observed.stale_tasks_count) - float(target.stale_tasks_count),
        "memory_fragmentation_index": float(observed.memory_fragmentation_index)
        - float(target.memory_fragmentation_index),
        "avg_latency_ms": float(observed.avg_latency_ms) - float(target.avg_latency_ms),
        "db_lock_events": float(observed.db_lock_events) - float(target.db_lock_events),
    }


def strix_compute_delta(
    metrics: CurrentMetrics | dict[str, Any],
    targets: HomeostasisTarget | dict[str, Any],
    *,
    use_sandbox: bool = False,
) -> dict[str, float]:
    del use_sandbox
    return compute_distance_vector(metrics, targets)
