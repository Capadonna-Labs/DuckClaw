"""Plan correction rules and JSON parser retry → noop."""

from __future__ import annotations

from harness_core.graphs.meditate_graph import _plan_rules
from harness_core.policies.corrective_allowlist import parse_corrective_actions_json


def test_plan_rules_circuit_breaker_above_50pct() -> None:
    actions = _plan_rules(
        {"error_rate_pct": 0},
        {"error_rate_pct": 55.0},
    )
    types = {a.action_type for a in actions}
    assert "circuit_breaker_pause" in types
    assert "alert_admin" in types


def test_plan_rules_stale_tasks_purge() -> None:
    actions = _plan_rules({"stale_tasks_count": 2.0}, {"error_rate_pct": 0})
    assert any(a.action_type == "purge_stale_tasks" for a in actions)


def test_parse_invalid_json_returns_noop() -> None:
    actions = parse_corrective_actions_json("not json at all")
    assert len(actions) == 1
    assert actions[0].action_type == "noop"


def test_parse_valid_json_array() -> None:
    raw = '[{"action_type":"noop","requires_hitl":false,"reason":"ok"}]'
    actions = parse_corrective_actions_json(raw)
    assert actions[0].action_type == "noop"
