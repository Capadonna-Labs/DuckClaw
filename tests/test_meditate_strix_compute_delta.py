"""Strix/deterministic distance vector for meditate."""

from __future__ import annotations

from harness_core.skills.strix_compute_delta import compute_distance_vector, strix_compute_delta
from harness_core.states.meditate_state import CurrentMetrics, HomeostasisTarget


def test_compute_distance_vector_positive_drift_only() -> None:
    metrics = CurrentMetrics(
        error_rate_pct=5.0,
        avg_latency_ms=6000.0,
        stale_tasks_count=3,
        memory_fragmentation_index=0.25,
        db_lock_events=2,
    )
    targets = HomeostasisTarget()
    dist = compute_distance_vector(metrics, targets)
    assert dist["error_rate_pct"] == 3.0
    assert dist["avg_latency_ms"] == 1000.0
    assert dist["stale_tasks_count"] == 3.0
    assert dist["memory_fragmentation_index"] == 0.1
    assert dist["db_lock_events"] == 2.0


def test_strix_compute_delta_local_fallback() -> None:
    metrics = CurrentMetrics(error_rate_pct=1.0)
    targets = HomeostasisTarget(error_rate_pct=2.0)
    dist = strix_compute_delta(metrics, targets, use_sandbox=False)
    assert dist["error_rate_pct"] == 0.0
