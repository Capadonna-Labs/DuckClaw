"""Meditate delta CLI and config key parsing."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from duckclaw.graphs.on_the_fly_commands import (
    _format_meditate_cycle_summary,
    _resolve_meditate_vault_user_id,
    chat_id_from_meditate_delta_config_key,
    clear_meditate_schedule,
    execute_meditate,
    get_chat_state,
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


def test_chat_id_from_meditate_delta_config_key() -> None:
    assert chat_id_from_meditate_delta_config_key("chat_42_meditate_delta_seconds") == "42"


def test_resolve_meditate_vault_user_id_private_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory,
) -> None:
    monkeypatch.setenv("CAPADONNA_DRILLER_ROOT", str(tmp_path))
    vault = tmp_path / "db" / "private" / "1726618406" / "quant_traderdb1.duckdb"
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


def test_execute_meditate_delta_off() -> None:
    db = _FakeDb()
    set_chat_state(db, "1", "meditate_delta_seconds", "3600")
    msg = execute_meditate(db, "1", "--delta off", tenant_id="default")
    assert "desactivado" in msg.lower()
    assert get_chat_state(db, "1", "meditate_delta_seconds") == "0"


def test_execute_meditate_schedule_requires_worker() -> None:
    db = _FakeDb()
    msg = execute_meditate(db, "9", "--delta 4h", tenant_id="t1")
    assert "worker" in msg.lower()


def test_execute_meditate_schedule_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    set_chat_state(db, "5", "worker_id", "Quant-Trader")
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.invoke_meditate_cycle_for_chat",
        lambda *_a, **_k: {"status": "completed"},
    )
    msg = execute_meditate(db, "5", "--delta 4h", tenant_id="cuantitativo")
    assert "4h" in msg
    assert "Primer ciclo:" in msg
    assert get_chat_state(db, "5", "meditate_delta_seconds") == "14400"
    assert get_chat_state(db, "5", "meditate_tenant_id") == "cuantitativo"
    assert float(get_chat_state(db, "5", "meditate_last_fire_epoch") or "0") > 0
    clear_meditate_schedule(db, "5")
    assert get_chat_state(db, "5", "meditate_delta_seconds") == "0"


def test_format_meditate_cycle_summary_alignment_message() -> None:
    cycle = {
        "status": "completed",
        "dispatched_actions": [{"action_type": "noop", "executed": True}],
        "alignment_message": (
            "Contexto alineado con las metas homeostasis. "
            "Metas: DD target=0.05 (obs: 0.01) ✓. Infra: sin desvíos infra."
        ),
    }
    summary = _format_meditate_cycle_summary(cycle)
    assert "Contexto alineado" in summary
    assert "DD target=0.05" in summary
