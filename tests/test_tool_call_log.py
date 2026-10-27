"""Audit row per external (MCP) tool call: typed command, DB-Writer handler, and the fire-and-forget recorder."""
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb

from duckclaw.write_commands import AppendToolCallLogCommand


def test_command_roundtrip_has_no_payload_fields() -> None:
    cmd = AppendToolCallLogCommand(tenant_id="t", id="TOOL-1", connector_id="mcp_tailscale", tool_name="list_devices", duration_ms=120, args_bytes=2, result_bytes=900)
    raw = json.loads(cmd.to_redis_payload())
    assert raw["command_type"] == "append_tool_call_log" and raw["status"] == "ok" and raw["duration_ms"] == 120
    assert not {"arguments", "args", "result", "payload"} & set(raw)          # sizes only: arguments and results can carry keys


def test_handler_inserts_the_row_and_clamps_the_fields() -> None:
    from duckclaw.write_handlers.usage_logs import _apply_append_tool_call_log

    con = duckdb.connect(":memory:")
    _apply_append_tool_call_log(con, {"id": "TOOL-1", "tenant_id": "t", "worker_id": "w", "connector_id": "c", "tool_name": "x" * 500, "status": "weird", "duration_ms": -5, "error": "e" * 500})
    row = con.execute("SELECT id, tenant_id, status, duration_ms, length(tool_name), length(error) FROM tool_call_log").fetchone()
    assert row == ("TOOL-1", "t", "ok", 0, 128, 160)                            # unknown status -> ok, negative -> 0, long text cut
    _apply_append_tool_call_log(con, {"id": "TOOL-2", "status": "error", "error": "timeout"})
    assert con.execute("SELECT status, tenant_id FROM tool_call_log WHERE id = 'TOOL-2'").fetchone() == ("error", "default")


def test_recorder_enqueues_a_typed_command_without_waiting(tmp_path, monkeypatch) -> None:
    from duckclaw import db_write_fire_and_forget
    from duckclaw.forge.skills import mcp_call_audit

    sent: list = []
    monkeypatch.setattr(db_write_fire_and_forget, "enqueue_write_command", lambda command, db_path, user_id: sent.append((command, db_path, user_id)) or "task-1")

    class Db:
        _path = str(tmp_path / "hub.duckdb")

    mcp_call_audit.record_mcp_call(Db(), {"connector_id": "mcp_x"}, "list_devices", status="ok", started=time.monotonic() - 0.25, args_bytes=2, result_bytes=40)
    (command, db_path, _uid), = sent
    assert command.connector_id == "mcp_x" and command.tool_name == "list_devices" and command.status == "ok"
    assert command.duration_ms >= 250 and command.args_bytes == 2 and command.result_bytes == 40 and Path(db_path).name == "hub.duckdb"


def test_recorder_never_raises_and_skips_memory_dbs(monkeypatch) -> None:
    from duckclaw import db_write_fire_and_forget
    from duckclaw.forge.skills import mcp_call_audit

    def boom(*_a, **_k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(db_write_fire_and_forget, "enqueue_write_command", boom)

    class Mem:
        _path = ":memory:"

    class Disk:
        _path = "hub.duckdb"

    mcp_call_audit.record_mcp_call(Mem(), {}, "t", status="ok", started=time.monotonic(), args_bytes=0)
    mcp_call_audit.record_mcp_call(Disk(), {}, "t", status="error", started=time.monotonic(), args_bytes=0, error="X")   # the failure is swallowed


def test_bridge_records_both_outcomes_of_every_connector_call() -> None:
    src = Path("packages/agents/src/duckclaw/forge/skills/mcp_connector_bridge.py").read_text(encoding="utf-8")
    body = src.split("def _sync_call")[1].split("desc = getattr")[0]
    assert body.count("record_mcp_call(") == 2 and "status=\"error\"" in body and "raise" in body   # a raised call is recorded, then re-raised
