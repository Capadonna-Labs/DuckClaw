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


def test_presets_include_higgsfield_and_stdio_profiles() -> None:
    presets = {p["preset_id"]: p for p in list_mcp_connector_presets()}
    assert "higgsfield" in presets
    assert presets["higgsfield"]["transport"] == "streamable_http"
    assert presets["higgsfield"]["endpoint_url"] == "https://mcp.higgsfield.ai/mcp"
    assert "mcp_fetch" in presets
    assert presets["mcp_fetch"]["transport"] == "stdio"
    assert preset_payload("unknown") is None


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
        "SELECT connector_id, transport, preset_id, auth_kind FROM main.admin_mcp_connectors"
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
        connector_id="mcp_higgsfield",
        preset_id="higgsfield",
    )
    assert cmd.command_type == "upsert_mcp_connector"
