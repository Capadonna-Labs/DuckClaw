"""Meditate cognitive scheduler CLI and config key parsing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from duckclaw.commands.meditate import build_meditate_self_system_event_message
from duckclaw.graphs.on_the_fly_commands import (
    _format_meditate_cycle_summary,
    _chat_key,
    _resolve_meditate_vault_user_id,
    chat_id_from_meditate_delta_config_key,
    clear_meditate_schedule,
    execute_meditate,
    get_chat_state,
    handle_command,
    set_chat_state,
)


class _FakeDb:
    def __init__(self) -> None:
        self._rows: dict[str, str] = {}

    def execute(self, sql: str) -> None:
        if "INSERT INTO agent_config" in sql:
            parts = sql.split("VALUES ('", 1)[1]
            key, rest = parts.split("', '", 1)
            val = rest.split("')", 1)[0]
            self._rows[key] = val.replace("''", "'")

    def query(self, sql: str):
        if "SELECT value FROM agent_config" in sql:
            key = sql.split("key = '", 1)[1].split("'", 1)[0]
            val = self._rows.get(key, "")
            return json.dumps([{"value": val}]) if val else json.dumps([])
        return json.dumps([])


@pytest.fixture
def mock_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Manifest:
        goals = []

        def model_dump(self):
            return {"goals": [], "infra": {}}

    monkeypatch.setattr(
        "harness_core.targets.load_homeostasis_manifest",
        lambda *_a, **_k: _Manifest(),
    )
    monkeypatch.setattr(
        "harness_core.targets.manifest_goals_as_dicts",
        lambda _m: [],
    )


def test_chat_id_from_meditate_delta_config_key() -> None:
    assert chat_id_from_meditate_delta_config_key("chat_42_meditate_delta_seconds") == "42"


def test_resolve_meditate_vault_user_id_private_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory,
) -> None:
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    vault = tmp_path / "db" / "private" / "1726618406" / "analyticsdb1.duckdb"
    vault.parent.mkdir(parents=True)
    vault.touch()
    db = MagicMock()
    db._path = str(vault)
    uid = _resolve_meditate_vault_user_id(
        db,
        vault_user_id="admin-conv-53ef9f0b34864d149b3414180625ae02",
        chat_id="admin-conv-53ef9f0b34864d149b3414180625ae02",
        tenant_id="user-juanjoarevalo57-79c5ca60b91d4f3e",
    )
    assert uid == "1726618406"


def test_build_meditate_self_system_event_message(mock_manifest: None) -> None:
    db = _FakeDb()
    msg = build_meditate_self_system_event_message(db, "1", "default", scheduled=True)
    assert "SYSTEM_EVENT" in msg
    assert "assess_crons_alignment" in msg
    assert "request_homeostasis_validation" in msg
    assert "programado /meditate" in msg


def test_execute_meditate_delta_off() -> None:
    db = _FakeDb()
    set_chat_state(db, "1", "meditate_delta_seconds", "3600")
    msg = execute_meditate(db, "1", "--delta off", tenant_id="default")
    assert "detenido" in msg.lower() or "desactivado" in msg.lower()
    assert get_chat_state(db, "1", "meditate_delta_seconds") == "0"


def test_execute_meditate_schedule_requires_worker() -> None:
    db = _FakeDb()
    msg = execute_meditate(db, "9", "--delta 4h", tenant_id="t1")
    assert "worker" in msg.lower()


def test_execute_meditate_schedule_ok() -> None:
    db = _FakeDb()
    set_chat_state(db, "5", "worker_id", "analytics-worker")
    msg = execute_meditate(db, "5", "--delta 4h", tenant_id="analytics")
    assert "4h" in msg
    assert "Auto-mejora" in msg
    assert get_chat_state(db, "5", "meditate_delta_seconds") == "14400"
    assert get_chat_state(db, "5", "meditate_tenant_id") == "analytics"
    assert float(get_chat_state(db, "5", "meditate_last_fire_epoch") or "0") > 0
    clear_meditate_schedule(db, "5")
    assert get_chat_state(db, "5", "meditate_delta_seconds") == "0"


def test_execute_meditate_delta_with_read_only_handle_queues_typed_commands(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus

    captured = []

    class ReadOnlyDb:
        _read_only = True

        def __init__(self) -> None:
            self._path = str(tmp_path / "vault.duckdb")
            self.released = 0
            self.resumed = 0
            self.direct_writes: list[str] = []

        def execute(self, sql: str) -> None:
            self.direct_writes.append(sql)
            raise AssertionError(f"read-only /meditate must not execute SQL directly: {sql}")

        def query(self, sql: str):
            if _chat_key("5", "worker_id") in sql:
                return json.dumps([{"value": "analytics-worker"}])
            return json.dumps([])

        def release_file_handle_for_external_writer(self) -> None:
            self.released += 1

        def resume_readonly_file_handle(self) -> None:
            self.resumed += 1

    def fake_enqueue(command, *, db_path: str, user_id: str) -> str:
        captured.append((command, db_path, user_id))
        return command.task_id

    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue)
    monkeypatch.setattr(
        "duckclaw.db_write_queue.poll_task_status_sync",
        lambda *_a, **_k: DbWriteTaskStatus(status="success"),
    )

    db = ReadOnlyDb()
    msg = execute_meditate(db, "5", "--delta 4h", tenant_id="analytics")

    merged_entries: dict[str, str] = {}
    for command, _db_path, user_id in captured:
        assert command.command_type == "upsert_agent_config_entries"
        assert command.tenant_id == "analytics"
        assert command.actor_email == "chat:5"
        assert user_id == "5"
        merged_entries.update(command.entries)
    assert "Auto-mejora meditate" in msg
    assert merged_entries[_chat_key("5", "meditate_delta_seconds")] == "14400"
    assert merged_entries[_chat_key("5", "meditate_tenant_id")] == "analytics"
    assert merged_entries[_chat_key("5", "meditate_worker_id")] == "analytics-worker"
    assert float(merged_entries[_chat_key("5", "meditate_last_fire_epoch")]) > 0
    assert db.direct_writes == []
    assert db.released >= 1
    assert db.resumed == db.resumed


def test_format_meditate_cycle_summary_alignment_message() -> None:
    cycle = {
        "status": "completed",
        "alignment_message": "Contexto alineado con las metas homeostasis.",
    }
    summary = _format_meditate_cycle_summary(cycle)
    assert "Contexto alineado" in summary


def test_format_meditate_next_tick_footer_disabled() -> None:
    from duckclaw.commands.meditate import format_meditate_next_tick_footer

    db = _FakeDb()
    footer = format_meditate_next_tick_footer(db, "7")
    assert "inactivo" in footer.lower()
    assert "`/meditate on`" in footer


def test_format_meditate_next_tick_footer_scheduled() -> None:
    from duckclaw.commands.meditate import format_meditate_next_tick_footer

    db = _FakeDb()
    set_chat_state(db, "7", "meditate_delta_seconds", "3600")
    # Ancla determinista: 1700000000 UTC (22:13:20Z) + 3600s = 23:13:20Z = 18:13 COT.
    set_chat_state(db, "7", "meditate_last_fire_epoch", "1700000000")
    footer = format_meditate_next_tick_footer(db, "7", now=1700001800.0)
    assert "auto-mejora meditate" in footer
    assert "18:13 COT" in footer
    assert "COT (en ~" in footer


def test_format_meditate_next_tick_footer_scheduled_no_anchor() -> None:
    from duckclaw.commands.meditate import format_meditate_next_tick_footer

    db = _FakeDb()
    set_chat_state(db, "9", "meditate_delta_seconds", "3600")
    # Sin last_fire: estima now + secs = 1700000000 + 3600 = 18:13 COT.
    footer = format_meditate_next_tick_footer(db, "9", now=1700000000.0)
    assert "~18:13 COT" in footer


def test_format_meditate_next_tick_footer_active_mode() -> None:
    from duckclaw.commands.meditate import format_meditate_next_tick_footer

    db = _FakeDb()
    set_chat_state(db, "3", "meditate_active", "1")
    set_chat_state(db, "3", "meditate_awaiting_user", "1")
    footer = format_meditate_next_tick_footer(db, "3")
    assert "esperando tu respuesta" in footer.lower()


def test_execute_meditate_on_turn_mode(mock_manifest: None, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    set_chat_state(db, "1", "worker_id", "analytics-worker")
    monkeypatch.setattr(
        "duckclaw.commands.meditate.dispatch_meditate_self_tick",
        lambda **_k: {"ok": True, "status_code": 202},
    )
    msg = execute_meditate(db, "1", "on", tenant_id="default")
    assert "activo" in msg.lower()
    assert get_chat_state(db, "1", "meditate_active") == "1"
    assert get_chat_state(db, "1", "meditate_delta_seconds") == "0"
    assert get_chat_state(db, "1", "meditate_worker_id") == "analytics-worker"


def test_execute_meditate_on_with_interval() -> None:
    db = _FakeDb()
    set_chat_state(db, "5", "worker_id", "analytics-worker")
    msg = execute_meditate(db, "5", "on 4h", tenant_id="analytics")
    assert "4h" in msg
    assert "Auto-mejora" in msg
    assert get_chat_state(db, "5", "meditate_delta_seconds") == "14400"
    assert get_chat_state(db, "5", "meditate_active") == "0"


def test_execute_meditate_off() -> None:
    db = _FakeDb()
    set_chat_state(db, "1", "meditate_delta_seconds", "3600")
    set_chat_state(db, "1", "meditate_active", "1")
    msg = execute_meditate(db, "1", "off", tenant_id="default")
    assert "detenido" in msg.lower() or "desactivado" in msg.lower()
    assert get_chat_state(db, "1", "meditate_delta_seconds") == "0"
    assert get_chat_state(db, "1", "meditate_active") == "0"


def test_meditate_bare_triggers_self(mock_manifest: None, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    set_chat_state(db, "42", "worker_id", "analytics-worker")
    monkeypatch.setattr(
        "duckclaw.commands.meditate.post_meditate_self_tick_sync",
        lambda **_k: {"ok": True, "status_code": 200},
    )
    msg = handle_command(db, "42", "/meditate", tenant_id="default")
    assert msg is not None
    assert "iniciado" in msg.lower()


def test_meditate_on_off_routed_by_fly(mock_manifest: None, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    set_chat_state(db, "42", "worker_id", "analytics-worker")
    monkeypatch.setattr(
        "duckclaw.commands.meditate.post_meditate_self_tick_sync",
        lambda **_k: {"ok": True, "status_code": 200},
    )
    on_msg = handle_command(db, "42", "/meditate on", tenant_id="default")
    assert on_msg is not None
    assert "activo" in on_msg.lower()
    assert get_chat_state(db, "42", "meditate_active") == "1"
    off_msg = handle_command(db, "42", "/meditate off", tenant_id="default")
    assert off_msg is not None
    assert "detenido" in off_msg.lower() or "desactivado" in off_msg.lower()
    assert get_chat_state(db, "42", "meditate_active") == "0"
    self_msg = handle_command(db, "42", "/meditate --self", tenant_id="default")
    assert self_msg is not None
    assert "iniciado" in self_msg.lower()


def test_is_meditate_footer_turn_fly_command() -> None:
    from core.chat_invoke_finalize import _is_meditate_footer_turn

    assert _is_meditate_footer_turn(
        user_incoming="/meditate",
        message="",
        fly_cmd="/meditate",
        cmd_name="meditate",
    )


def test_is_meditate_footer_turn_ciclo_label() -> None:
    from core.chat_invoke_finalize import _is_meditate_footer_turn
    from duckclaw.commands.meditate import MEDITATE_SYSTEM_USER_LABEL

    assert _is_meditate_footer_turn(
        user_incoming=MEDITATE_SYSTEM_USER_LABEL,
        message="[SYSTEM_EVENT: Validación HITL pendiente]",
        fly_cmd=MEDITATE_SYSTEM_USER_LABEL,
        cmd_name="",
    )


def test_is_meditate_footer_turn_negative() -> None:
    from core.chat_invoke_finalize import _is_meditate_footer_turn

    assert not _is_meditate_footer_turn(
        user_incoming="hola",
        message="¿cómo va el proyecto?",
        fly_cmd="hola",
        cmd_name="",
    )


def test_build_meditate_tick_payload_includes_vault() -> None:
    from duckclaw.commands.meditate import _build_meditate_tick_payload

    payload = _build_meditate_tick_payload(
        chat_id="admin-conv-abc",
        tenant_id="tenant-x",
        message="[SYSTEM_EVENT: test]",
        vault_db_path="/tmp/session_vault.duckdb",
    )
    assert payload.get("vault_db_path") == "/tmp/session_vault.duckdb"
    assert payload.get("tenant_id") == "tenant-x"
