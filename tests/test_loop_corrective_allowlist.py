"""Zero-trust corrective action allowlist."""

from __future__ import annotations

import pytest

from harness_core.policies.corrective_allowlist import normalize_corrective_action


def test_rejects_unknown_action_type() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        normalize_corrective_action({"action_type": "drop_table", "requires_hitl": False, "reason": "x"})


def test_coerces_hitl_for_circuit_breaker() -> None:
    action = normalize_corrective_action(
        {"action_type": "circuit_breaker_pause", "requires_hitl": False, "reason": "high errors"}
    )
    assert action.requires_hitl is True


def test_purge_stale_not_hitl() -> None:
    action = normalize_corrective_action(
        {"action_type": "purge_stale_tasks", "requires_hitl": True, "reason": "stale"}
    )
    assert action.requires_hitl is False
