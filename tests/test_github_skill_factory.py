"""Tests for GitHub MCP skill registration in worker factory."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_build_worker_tools_invokes_github_skill_when_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])
    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        lambda *args, **kwargs: None,
    )

    calls: list[dict] = []

    def _fake_register_github(tools, cfg, **kwargs):
        calls.append({"tools": tools, "cfg": cfg, **kwargs})

    monkeypatch.setattr("duckclaw.github.mcp_bridge.register_github_skill", _fake_register_github)

    spec = SimpleNamespace(
        worker_id="dev-agent",
        logical_worker_id="dev-agent",
        worker_slug="dev-agent",
        name="Dev Agent",
        schema_name="main",
        allowed_tables=[],
        read_only=True,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
        skills_list=["github"],
        skill_configs={"github": {"enabled": True}},
    )
    db = MagicMock()
    db.query = MagicMock(return_value="[]")

    _build_worker_tools(db, spec)  # type: ignore[arg-type]

    assert len(calls) == 1
    assert calls[0]["cfg"] == {"enabled": True}
    assert calls[0]["logical_worker_id"] == "dev-agent"
