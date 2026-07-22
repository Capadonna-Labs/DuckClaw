"""Unit tests for MCP connector presets and write handlers."""

from __future__ import annotations

import duckdb
import tempfile
from pathlib import Path

import pytest

from duckclaw.mcp_connector_presets import list_mcp_connector_presets, preset_payload
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_commands import UpsertMcpConnectorCommand
from duckclaw.write_handlers.mcp_connectors import _apply_upsert_mcp_connector


def test_presets_include_remote_http_oauth_and_stdio_profiles() -> None:
    from duckclaw.mcp_connector_presets import default_mcp_connector_preset_ids

    presets = {p["preset_id"]: p for p in list_mcp_connector_presets()}
    assert "remote_http_oauth" in presets
    assert default_mcp_connector_preset_ids() == []
    assert presets["remote_http_oauth"]["transport"] == "streamable_http"
    assert presets["remote_http_oauth"]["metadata"]["oauth_pkce"] is True
    assert presets["remote_http_oauth"]["metadata"]["manifest_skill_id"] == "higgsfield"
    assert "mcp_fetch" in presets
    assert presets["mcp_fetch"]["transport"] == "stdio"
    assert presets["mcp_fetch"]["launch_command"] == "npx"
    assert preset_payload("unknown") is None


def test_default_mcp_connector_id_is_stable() -> None:
    from duckclaw.mcp_connector_presets import default_mcp_connector_id

    assert default_mcp_connector_id("remote_http_oauth") == "mcp_remote_http_oauth"
    assert default_mcp_connector_id("notion", tenant_id="tenant-acme") == "mcp_notion"


def test_upsert_mcp_connector_from_preset_uses_stable_id() -> None:
    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "mcp.duckdb"))
    run_pending_migrations(con)

    _apply_upsert_mcp_connector(
        con,
        {
            "tenant_id": "default",
            "actor_email": "admin@test.local",
            "preset_id": "mcp_time",
            "connector_id": "",
        },
    )
    row = con.execute(
        "SELECT connector_id, transport, preset_id, auth_kind FROM main.admin_mcp_connectors "
        "WHERE connector_id = 'mcp_mcp_time'"
    ).fetchone()
    assert row is not None
    assert row[0] == "mcp_mcp_time"
    assert row[1] == "stdio"
    assert row[2] == "mcp_time"
    assert row[3] == "none"
    con.close()


def test_upsert_mcp_connector_command_registered() -> None:
    cmd = UpsertMcpConnectorCommand(
        tenant_id="default",
        actor_email="admin@test.local",
        connector_id="mcp_remote_http_oauth",
        preset_id="remote_http_oauth",
    )
    assert cmd.command_type == "upsert_mcp_connector"


def test_ensure_admin_mcp_connectors_schema_skips_migrations_on_read_only() -> None:
    from duckclaw.admin_mcp_connectors import ensure_admin_mcp_connectors_schema

    class _RoDb:
        _read_only = True

        def execute(self, sql: str) -> None:
            raise AssertionError(f"read-only path must not execute DDL: {sql!r}")

    ensure_admin_mcp_connectors_schema(_RoDb())


def test_list_mcp_connectors_accepts_list_from_duckclaw_execute() -> None:
    from duckclaw.admin_mcp_connectors import list_mcp_connectors

    class _Db:
        _read_only = True

        def execute(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
            assert "admin_mcp_connectors" in sql
            return []

    assert list_mcp_connectors(_Db(), tenant_id="default") == []
