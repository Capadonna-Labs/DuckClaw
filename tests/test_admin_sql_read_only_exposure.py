"""admin_sql must register on read_only workers when tool_surface exposes it."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_read_only_worker_registers_admin_sql_when_tool_surface_exposes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])
    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        lambda *args, **kwargs: None,
    )

    spec = SimpleNamespace(
        worker_id="read_only_worker",
        logical_worker_id="read_only_worker",
        name="Read Only Worker",
        schema_name="main",
        allowed_tables=[],
        read_only=True,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
        skills_list=["admin_sql", "read_sql"],
        tool_surface_config={"expose_privileged_mutation_tools": ["admin_sql"]},
    )
    db = MagicMock()
    db.query = MagicMock(return_value="[]")

    tools = _build_worker_tools(db, spec)  # type: ignore[arg-type]
    tool_names = {getattr(t, "name", "") for t in tools}

    assert "admin_sql" in tool_names


def test_read_only_worker_without_tool_surface_omits_admin_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])
    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        lambda *args, **kwargs: None,
    )

    spec = SimpleNamespace(
        worker_id="ro-agent",
        logical_worker_id="ro-agent",
        name="RO Agent",
        schema_name="main",
        allowed_tables=[],
        read_only=True,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
        skills_list=["read_sql"],
        tool_surface_config=None,
    )
    db = MagicMock()
    db.query = MagicMock(return_value="[]")

    tools = _build_worker_tools(db, spec)  # type: ignore[arg-type]
    tool_names = {getattr(t, "name", "") for t in tools}

    assert "admin_sql" not in tool_names
