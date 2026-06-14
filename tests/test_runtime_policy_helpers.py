from __future__ import annotations

import importlib
import importlib.util
from types import SimpleNamespace

import pytest


def _runtime_policy(*, name: str, policy: dict | None = None):
    from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy

    capability = WorkerCapability(
        capability_id=f"cap_{name}",
        name=name,
        kind="runtime_policy",
        provider="duckclaw",
        permission="use",
        config={},
        policy=policy or {},
        quota={},
    )
    return WorkerRuntimePolicy(
        worker_id="worker_alpha",
        identity=None,
        capabilities=(capability,),
    )


def test_runtime_policy_helpers_module_exposes_worker_policy_api() -> None:
    module_spec = importlib.util.find_spec("duckclaw.workers.runtime_policy_helpers")
    assert module_spec is not None

    helpers = importlib.import_module("duckclaw.workers.runtime_policy_helpers")
    spec = SimpleNamespace(runtime_policy=_runtime_policy(name="field_reflection"))

    assert helpers.worker_runtime_policy(spec) is spec.runtime_policy
    assert helpers.worker_has_runtime_capability(spec, "field_reflection")
    assert not helpers.worker_has_runtime_capability(spec, "bounded_json_read")
    assert not helpers.worker_has_runtime_capability(SimpleNamespace(runtime_policy=None), "field_reflection")


def test_runtime_capability_flag_coerces_policy_values() -> None:
    helpers = importlib.import_module("duckclaw.workers.runtime_policy_helpers")
    spec = SimpleNamespace(
        runtime_policy=_runtime_policy(
            name="portfolio_live_bridge",
            policy={
                "enabled_by_default": "true",
                "disabled_by_default": "off",
                "numeric_enabled": 1,
                "empty_value": None,
                "unknown_text": "maybe",
            },
        )
    )

    assert helpers.worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "enabled_by_default",
        default=False,
    )
    assert not helpers.worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "disabled_by_default",
        default=True,
    )
    assert helpers.worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "numeric_enabled",
        default=False,
    )
    assert helpers.worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "empty_value",
        default=True,
    )
    assert not helpers.worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "unknown_text",
        default=False,
    )


def test_worker_use_heuristic_first_tool_prefers_manifest_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helpers = importlib.import_module("duckclaw.workers.runtime_policy_helpers")

    monkeypatch.setenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", "false")
    assert helpers.worker_use_heuristic_first_tool(
        SimpleNamespace(agent_node_heuristic_first_tool=True)
    ) is True

    monkeypatch.setenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", "true")
    assert helpers.worker_use_heuristic_first_tool(
        SimpleNamespace(agent_node_heuristic_first_tool=False)
    ) is False

    monkeypatch.delenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", raising=False)
    assert helpers.worker_use_heuristic_first_tool(
        SimpleNamespace(agent_node_heuristic_first_tool=None)
    ) is True
