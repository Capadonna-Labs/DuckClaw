"""Tests for worker-to-worker allowed_delegates invoke."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.workers.manifest import WorkerSpec, _parse_allowed_delegates, build_spec_from_manifest


def test_manifest_parses_allowed_delegates() -> None:
    data = {
        "id": "quant_trader",
        "skills": [],
        "allowed_delegates": ["quant_reporter", "quant-reporter"],
    }
    spec = build_spec_from_manifest(data, "quant_trader", Path("/tmp/w"))
    assert "quant_reporter" in spec.allowed_delegates
    assert len(spec.allowed_delegates) == 1


def test_parse_allowed_delegates_empty() -> None:
    assert _parse_allowed_delegates({}) == ()
    assert _parse_allowed_delegates({"allowed_delegates": "a, b"}) == ("a", "b")


def test_invoke_delegated_worker_rejects_not_in_allowlist() -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker

    caller_spec = WorkerSpec(
        worker_id="quant_trader",
        logical_worker_id="quant_trader",
        name="qt",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.1,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=True,
        worker_dir=Path("/tmp"),
        allowed_delegates=("quant_reporter",),
    )
    result = invoke_delegated_worker(
        caller_worker_id="quant_trader",
        caller_spec=caller_spec,
        target_worker_id="other_worker",
        task="build dashboard",
        state={"chat_id": "chat-1", "tenant_id": "default"},
        db=MagicMock(),
        llm=None,
        templates_root=None,
        tenant_id="default",
    )
    assert result.status == "error"
    assert result.error == "not_allowed"


def test_invoke_delegated_worker_rejects_nested_depth() -> None:
    from duckclaw.workers import worker_invoke as wi

    caller_spec = SimpleNamespace(allowed_delegates=("quant_reporter",))
    wi._delegate_depth.set(1)
    try:
        result = wi.invoke_delegated_worker(
            caller_worker_id="quant_trader",
            caller_spec=caller_spec,
            target_worker_id="quant_reporter",
            task="nested",
            state={"chat_id": "chat-1"},
            db=MagicMock(),
            llm=None,
            templates_root=None,
            tenant_id="default",
        )
    finally:
        wi._delegate_depth.set(0)
    assert result.status == "error"
    assert result.error == "depth_exceeded"


@patch("duckclaw.workers.factory.build_worker_graph")
def test_invoke_delegated_worker_success_with_report_id(mock_build_graph: MagicMock) -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker
    from langchain_core.messages import ToolMessage

    graph = MagicMock()
    graph.invoke.return_value = {
        "reply": "Dashboard listo.",
        "messages": [
            ToolMessage(
                content='{"status": "success", "report_id": "chat-abc"}',
                name="publish_custom_report",
                tool_call_id="1",
            )
        ],
    }
    mock_build_graph.return_value = graph

    caller_spec = SimpleNamespace(allowed_delegates=("quant_reporter",))
    with patch("duckclaw.workers.manifest.load_manifest", return_value=SimpleNamespace(forge_vault_binding=None)):
        result = invoke_delegated_worker(
            caller_worker_id="quant_trader",
            caller_spec=caller_spec,
            target_worker_id="quant_reporter",
            task="report_id=chat-abc publish html dashboard",
            state={"chat_id": "chat-abc", "tenant_id": "default", "user_id": "u1"},
            db=MagicMock(),
            llm=MagicMock(),
            templates_root=None,
            tenant_id="default",
        )
    assert result.status == "success"
    assert result.report_id == "chat-abc"
    assert "Dashboard" in result.reply


def test_build_worker_tools_omits_write_output_when_allowed_delegates() -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    spec = WorkerSpec(
        worker_id="quant_trader",
        logical_worker_id="quant_trader",
        name="qt",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.1,
        topology="general",
        skills_list=["read_sql"],
        allowed_tables=[],
        read_only=True,
        worker_dir=Path("/tmp"),
        allowed_delegates=("quant_reporter",),
    )
    tools = _build_worker_tools(MagicMock(), spec)  # type: ignore[arg-type]
    names = {t.name for t in tools}
    assert "invoke_worker" in names
    assert "write_output_document" not in names


def test_dashboard_html_intent_forces_invoke_worker() -> None:
    from duckclaw.workers.tool_orchestration import match_intent, parse_tool_orchestration

    spec = SimpleNamespace(
        tool_orchestration_config={
            "intents": {
                "dashboard_html": {
                    "patterns": ["(?i)dashboard.*html"],
                    "force_first_tool": "invoke_worker",
                }
            }
        }
    )
    orch = parse_tool_orchestration(spec)
    assert orch is not None
    assert match_intent("Generá y publicá un dashboard HTML con métricas", orch) == "dashboard_html"
