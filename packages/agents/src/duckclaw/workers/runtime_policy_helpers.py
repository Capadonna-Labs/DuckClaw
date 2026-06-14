"""Pure helpers for DB-backed worker runtime policies."""

from __future__ import annotations

import os
from typing import Any


def worker_use_heuristic_first_tool(spec: Any) -> bool:
    """Manifest ``agent_node.heuristic_first_tool`` wins over the environment default."""
    override = getattr(spec, "agent_node_heuristic_first_tool", None)
    if isinstance(override, bool):
        return override
    raw = (os.getenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def worker_runtime_policy(spec: Any) -> Any:
    """Return the DB-backed runtime policy attached to a worker spec, if available."""
    return getattr(spec, "runtime_policy", None)


def worker_has_runtime_capability(spec: Any, capability_name: str) -> bool:
    """DB-first capability gate; intentionally avoids worker-name fallbacks."""
    runtime_policy = worker_runtime_policy(spec)
    has_capability = getattr(runtime_policy, "has_capability", None)
    if not callable(has_capability):
        return False
    try:
        return bool(has_capability(capability_name))
    except Exception:
        return False


def worker_runtime_capability_policy(spec: Any, capability_name: str) -> dict[str, Any]:
    runtime_policy = worker_runtime_policy(spec)
    policy_for = getattr(runtime_policy, "policy_for", None)
    if not callable(policy_for):
        return {}
    try:
        policy = policy_for(capability_name)
    except Exception:
        return {}
    return dict(policy) if isinstance(policy, dict) else {}


def worker_runtime_capability_flag(
    spec: Any,
    capability_name: str,
    key: str,
    *,
    default: bool = False,
) -> bool:
    value = worker_runtime_capability_policy(spec, capability_name).get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    if raw in ("true", "1", "yes", "on"):
        return True
    return default
