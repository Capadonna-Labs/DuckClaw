"""admin_sql must refuse writes to custom_reports; publish_custom_report is the only writer.

Regression for a live incident (2026-09-06): a worker told not to use its usual tools wrote
a row into main.custom_reports via a raw admin_sql INSERT, bypassing publish_custom_report
entirely (its own tool description calls itself the sole writer for that table).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _spec(**overrides: object) -> SimpleNamespace:
    base = dict(
        worker_id="w",
        logical_worker_id="w",
        name="W",
        schema_name="main",
        allowed_tables=[],
        read_only=False,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
        skills_list=["admin_sql", "read_sql"],
        tool_surface_config=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _admin_sql_tool(monkeypatch: pytest.MonkeyPatch, db: MagicMock):
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])
    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        lambda *args, **kwargs: None,
    )
    tools = _build_worker_tools(db, _spec())  # type: ignore[arg-type]
    by_name = {getattr(t, "name", ""): t for t in tools}
    assert "admin_sql" in by_name
    return by_name["admin_sql"]


def test_worker_admin_sql_blocks_insert_into_custom_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.query = MagicMock(return_value="[]")
    db.execute = MagicMock()
    tool = _admin_sql_tool(monkeypatch, db)

    out = json.loads(
        tool.invoke(
            {"query": "INSERT INTO main.custom_reports (report_id, html_content) VALUES ('x','<html></html>')"}
        )
    )

    assert "error" in out
    assert "publish_custom_report" in out["error"]
    db.execute.assert_not_called()


def test_worker_admin_sql_blocks_update_custom_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.query = MagicMock(return_value="[]")
    db.execute = MagicMock()
    tool = _admin_sql_tool(monkeypatch, db)

    out = json.loads(tool.invoke({"query": "UPDATE custom_reports SET html_content = 'x' WHERE report_id = 'y'"}))

    assert "error" in out
    assert "publish_custom_report" in out["error"]
    db.execute.assert_not_called()


def test_worker_admin_sql_allows_writes_to_other_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.query = MagicMock(return_value="[]")
    db.execute = MagicMock()
    db._path = "/tmp/fake.duckdb"
    db._read_only = False
    tool = _admin_sql_tool(monkeypatch, db)

    out = json.loads(tool.invoke({"query": "INSERT INTO main.some_other_table (id) VALUES (1)"}))

    assert out.get("status") == "success"
    db.execute.assert_called_once()


def test_generic_admin_sql_blocks_writes_to_custom_reports() -> None:
    from duckclaw.graphs.tools import admin_sql

    db = MagicMock()
    db.execute = MagicMock()
    out = json.loads(admin_sql(db, "DELETE FROM custom_reports WHERE report_id = 'y'"))

    assert "error" in out
    assert "publish_custom_report" in out["error"]
    db.execute.assert_not_called()


def test_generic_admin_sql_allows_reads_of_custom_reports() -> None:
    from duckclaw.graphs.tools import admin_sql

    db = MagicMock()
    db.query = MagicMock(return_value="[]")
    out = admin_sql(db, "SELECT * FROM custom_reports WHERE report_id = 'y'")

    assert out == "[]"
    db.query.assert_called_once()
