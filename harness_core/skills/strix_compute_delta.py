"""Deterministic distance vector between current metrics and homeostasis targets."""

from __future__ import annotations

import json
import logging
from typing import Any

from harness_core.states.meditate_state import CurrentMetrics, HomeostasisTarget

_log = logging.getLogger(__name__)

_STRIX_SCRIPT = """
import json
import sys

metrics = json.loads(sys.stdin.read())
targets = metrics.pop("_targets")

def delta(curr, tgt, higher_is_bad=True):
    if higher_is_bad:
        return max(0.0, float(curr) - float(tgt))
    return max(0.0, float(tgt) - float(curr))

out = {
    "error_rate_pct": delta(metrics["error_rate_pct"], targets["error_rate_pct"]),
    "avg_latency_ms": delta(metrics["avg_latency_ms"], targets["avg_latency_ms"]),
    "stale_tasks_count": delta(metrics["stale_tasks_count"], targets["stale_tasks_count"]),
    "memory_fragmentation_index": delta(
        metrics["memory_fragmentation_index"], targets["memory_fragmentation_index"]
    ),
    "db_lock_events": delta(metrics["db_lock_events"], targets["db_lock_events"]),
}
print(json.dumps(out))
"""


def compute_distance_vector(
    metrics: CurrentMetrics | dict[str, Any],
    targets: HomeostasisTarget | dict[str, Any],
) -> dict[str, float]:
    """Pure-Python homeostasis distance (positive = drift from target)."""
    m = metrics if isinstance(metrics, CurrentMetrics) else CurrentMetrics.model_validate(metrics)
    t = targets if isinstance(targets, HomeostasisTarget) else HomeostasisTarget.model_validate(targets)

    def _delta(curr: float, tgt: float) -> float:
        return max(0.0, float(curr) - float(tgt))

    return {
        "error_rate_pct": _delta(m.error_rate_pct, t.error_rate_pct),
        "avg_latency_ms": _delta(m.avg_latency_ms, t.avg_latency_ms),
        "stale_tasks_count": _delta(float(m.stale_tasks_count), float(t.stale_tasks_count)),
        "memory_fragmentation_index": _delta(m.memory_fragmentation_index, t.memory_fragmentation_index),
        "db_lock_events": _delta(float(m.db_lock_events), float(t.db_lock_events)),
    }


def strix_compute_delta(
    metrics: CurrentMetrics | dict[str, Any],
    targets: HomeostasisTarget | dict[str, Any],
    *,
    db: Any | None = None,
    use_sandbox: bool = True,
) -> dict[str, float]:
    """
    Compute distance via fixed Strix script when Docker sandbox is available;
    falls back to local deterministic compute (no LLM).
    """
    if not use_sandbox:
        return compute_distance_vector(metrics, targets)

    try:
        from duckclaw.graphs.sandbox import _docker_available, run_in_sandbox

        if not _docker_available():
            return compute_distance_vector(metrics, targets)

        m = metrics if isinstance(metrics, CurrentMetrics) else CurrentMetrics.model_validate(metrics)
        t = targets if isinstance(targets, HomeostasisTarget) else HomeostasisTarget.model_validate(targets)
        payload = {**m.model_dump(), "_targets": t.model_dump()}
        stdin_json = json.dumps(payload, ensure_ascii=False)
        code = (
            "import json, sys\n"
            f"metrics = json.loads({json.dumps(stdin_json)})\n"
            "targets = metrics.pop('_targets')\n"
            "def delta(curr, tgt): return max(0.0, float(curr) - float(tgt))\n"
            "out = {\n"
            '  "error_rate_pct": delta(metrics["error_rate_pct"], targets["error_rate_pct"]),\n'
            '  "avg_latency_ms": delta(metrics["avg_latency_ms"], targets["avg_latency_ms"]),\n'
            '  "stale_tasks_count": delta(metrics["stale_tasks_count"], targets["stale_tasks_count"]),\n'
            '  "memory_fragmentation_index": delta(metrics["memory_fragmentation_index"], targets["memory_fragmentation_index"]),\n'
            '  "db_lock_events": delta(metrics["db_lock_events"], targets["db_lock_events"]),\n'
            "}\n"
            "print(json.dumps(out))\n"
        )
        result = run_in_sandbox(
            db,
            llm=None,
            code=code,
            max_retries=0,
            worker_id="harness-meditate",
            inject_python_header=False,
        )
        if result.exit_code != 0:
            _log.debug("strix_compute_delta sandbox failed: %s", result.stderr)
            return compute_distance_vector(metrics, targets)
        line = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""
        if not line:
            return compute_distance_vector(metrics, targets)
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            return {k: float(v) for k, v in parsed.items()}
    except Exception as exc:
        _log.debug("strix_compute_delta fallback: %s", exc)
    return compute_distance_vector(metrics, targets)
