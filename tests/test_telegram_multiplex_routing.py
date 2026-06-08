"""Tests: heurística de primera tool en nodo agent (manifest/env)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.workers.factory import _worker_use_heuristic_first_tool
from duckclaw.workers.manifest import WorkerSpec


def _minimal_spec(*, agent_node_heuristic_first_tool: bool | None = None) -> WorkerSpec:
    return WorkerSpec(
        worker_id="default",
        logical_worker_id="default_agent",
        name="Default",
        schema_name="agent_worker",
        llm_required=None,
        temperature=0.2,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=False,
        worker_dir=Path("."),
        agent_node_heuristic_first_tool=agent_node_heuristic_first_tool,
    )


def test_worker_use_heuristic_first_tool_default_env_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", raising=False)
    assert _worker_use_heuristic_first_tool(_minimal_spec()) is True


def test_worker_use_heuristic_first_tool_env_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", "false")
    assert _worker_use_heuristic_first_tool(_minimal_spec()) is False


def test_worker_use_heuristic_first_tool_manifest_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", "false")
    assert _worker_use_heuristic_first_tool(
        _minimal_spec(agent_node_heuristic_first_tool=True)
    ) is True
    monkeypatch.setenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL", "true")
    assert _worker_use_heuristic_first_tool(
        _minimal_spec(agent_node_heuristic_first_tool=False)
    ) is False
