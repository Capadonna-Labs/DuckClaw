"""Directives activated by bound tools come from DB metadata (when_tools), not core tool lists."""

from __future__ import annotations

import json
from types import SimpleNamespace

import duckdb

from duckclaw.prompt_policies.system_prompt import append_tool_triggered_directives


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE main.prompt_policy_registry (
            policy_type VARCHAR, policy_name VARCHAR, version INTEGER, status VARCHAR,
            active BOOLEAN, content TEXT, metadata_json TEXT
        )
        """
    )
    rows = [
        ("directive", "widget_rules", 1, "active", True, "## WIDGET RULES", {"when_tools": ["widget_"]}),
        ("directive", "always_off", 1, "inactive", False, "## OFF", {"when_tools": ["widget_"]}),
        ("directive", "no_trigger", 1, "active", True, "## NO TRIGGER", {}),
    ]
    for ptype, name, ver, status, active, content, meta in rows:
        con.execute(
            "INSERT INTO main.prompt_policy_registry VALUES (?, ?, ?, ?, ?, ?, ?)",
            [ptype, name, ver, status, active, content, json.dumps(meta)],
        )
    return con


def _tools(*names: str) -> list:
    return [SimpleNamespace(name=n) for n in names]


def test_matching_tool_appends_only_active_triggered_directive() -> None:
    out = append_tool_triggered_directives(_db(), "BASE", _tools("read_sql", "widget_create"))
    assert out.startswith("BASE") and "## WIDGET RULES" in out
    assert "## OFF" not in out and "## NO TRIGGER" not in out


def test_no_matching_tool_keeps_base() -> None:
    assert append_tool_triggered_directives(_db(), "BASE", _tools("read_sql")) == "BASE"


def test_threejs_directive_ships_in_the_framework_pack_and_triggers_on_report_publishing() -> None:
    from duckclaw.framework_policy_pack import load_framework_policy_pack

    entry = next(p for p in load_framework_policy_pack()["policies"] if p["policy_name"] == "threejs_reports")
    assert entry["policy_type"] == "directive" and entry["metadata"]["when_tools"] == ["publish_custom_report"]
    assert "three@0.186.1" in entry["content"] and "unpkg.com" in entry["content"] and len(entry["content"]) < 2500
    out = append_tool_triggered_directives(_db(), "BASE", _tools("publish_custom_report"))
    assert out == "BASE"          # the DB fixture has no such row: the trigger comes from the policy's own metadata, not a hardcoded tool list
