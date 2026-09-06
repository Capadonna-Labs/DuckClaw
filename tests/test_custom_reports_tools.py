"""Tests for custom reports tool registration in worker factory."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_build_worker_tools_registers_publish_custom_report_when_skill_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])
    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        lambda *args, **kwargs: None,
    )

    spec = SimpleNamespace(
        worker_id="report-agent",
        logical_worker_id="report-agent",
        name="Report Agent",
        schema_name="main",
        allowed_tables=[],
        read_only=True,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
        skills_list=["publish_custom_report"],
    )
    db = MagicMock()
    db.query = MagicMock(return_value="[]")

    tools = _build_worker_tools(db, spec)  # type: ignore[arg-type]
    tool_names = {getattr(t, "name", "") for t in tools}

    assert "publish_custom_report" in tool_names


def test_publish_custom_report_rejects_report_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from duckclaw.forge.skills.custom_reports_bridge import _publish_custom_report_impl
    from duckclaw.forge.skills import knowledge_tool_context as ktc

    html = "<!DOCTYPE html><html><body><h1>OK</h1></body></html>"
    audit_calls: list[tuple] = []

    monkeypatch.setattr(
        "duckclaw.forge.skills.custom_reports_bridge._audit_publish_report_id_rejected",
        lambda db, **kw: audit_calls.append((db, kw)),
    )
    ktc.set_session_chat_id("admin-conv-smoke3-abc")

    raw = _publish_custom_report_impl(
        MagicMock(),
        report_id="test-123",
        html_content=html,
    )
    data = json.loads(raw)
    assert data["status"] == "error"
    assert data["error"] == "report_id_mismatch"
    assert data["expected_report_id"] == "admin-conv-smoke3-abc"
    assert audit_calls
    assert audit_calls[0][1]["report_id"] == "test-123"


def test_publish_custom_report_accepts_matching_chat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from duckclaw.forge.skills.custom_reports_bridge import _publish_custom_report_impl
    from duckclaw.forge.skills import knowledge_tool_context as ktc

    html = "<!DOCTYPE html><html><body><h1>OK</h1></body></html>"
    pushed: list[dict] = []

    def _fake_push(payload, **kwargs):
        pushed.append(payload)
        return True

    monkeypatch.setattr(
        "duckclaw.forge.skills.reports_state_delta.push_reports_state_delta_sync",
        _fake_push,
    )
    monkeypatch.setenv("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", "/tmp/vault.duckdb")
    ktc.set_session_chat_id("admin-conv-smoke3-abc")

    raw = _publish_custom_report_impl(
        MagicMock(),
        report_id="admin-conv-smoke3-abc",
        html_content=html,
    )
    data = json.loads(raw)
    assert data["status"] == "success"
    assert pushed
    assert pushed[0]["mutation"]["report_id"] == "admin-conv-smoke3-abc"
