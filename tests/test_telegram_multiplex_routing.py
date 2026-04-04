"""Tests: A2A routing con Finanz en equipo y heurística de primera tool (manifest/env)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.graphs.manager_graph import route_finanz_reply_a2a_branch
from duckclaw.workers.factory import _worker_use_heuristic_first_tool
from duckclaw.workers.manifest import WorkerSpec


def _minimal_spec(*, agent_node_heuristic_first_tool: bool | None = None) -> WorkerSpec:
    return WorkerSpec(
        worker_id="finanz",
        logical_worker_id="finanz",
        name="Finanz",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.2,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=False,
        worker_dir=Path("."),
        agent_node_heuristic_first_tool=agent_node_heuristic_first_tool,
    )


def test_route_finanz_reply_a2a_branch_none_without_finanz_on_team() -> None:
    st = {
        "available_templates": ["Job-Hunter"],
        "assigned_worker_id": "finanz",
        "last_worker_raw_reply": "texto [a2a_request: income_injection] más",
    }
    assert route_finanz_reply_a2a_branch(st) is None


def test_route_finanz_reply_a2a_branch_income_injection_when_finanz_on_team() -> None:
    st = {
        "available_templates": ["finanz", "job_hunter"],
        "assigned_worker_id": "finanz",
        "last_worker_raw_reply": "ok [a2a_request: income_injection]",
    }
    assert route_finanz_reply_a2a_branch(st) == "handoff_to_target"


def test_route_finanz_reply_a2a_branch_job_track_when_finanz_on_team() -> None:
    st = {
        "available_templates": ["finanz", "Job-Hunter"],
        "assigned_worker_id": "finanz",
        "last_worker_raw_reply": "[a2a_request: job_opportunity_tracking]",
    }
    assert route_finanz_reply_a2a_branch(st) == "handoff_job_track"


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
