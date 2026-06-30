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
