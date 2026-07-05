"""Tests for /forget when called via API gateway (session_id) vs Telegram (chat_id)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from duckclaw.db_write_queue import DbWriteTaskStatus
from duckclaw.graphs.on_the_fly_commands import execute_forget


def _mock_db() -> MagicMock:
    """Minimal db mock with execute/query for on_the_fly_commands."""
    db = MagicMock()
    db._read_only = False
    db.query.return_value = "[]"
    return db


def test_forget_via_api_with_session_id_default_succeeds() -> None:
    """Fix: /forget via API with session_id='default' succeeds and deletes api_conversation."""
    db = _mock_db()
    result = execute_forget(db, "default")
    assert "✅" in result
    assert "Error" not in result
    call_args = [str(c) for c in db.execute.call_args_list]
    assert any("api_conversation" in a for a in call_args)


def test_forget_via_telegram_deletes_telegram_conversation() -> None:
    """Telegram: numeric chat_id deletes telegram_conversation."""
    db = _mock_db()
    result = execute_forget(db, "12345")
    assert "✅" in result
    call_args = [str(c) for c in db.execute.call_args_list]
    assert any("telegram_conversation" in a for a in call_args)


def test_forget_with_read_only_handle_uses_typed_command_and_preserves_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class ReadOnlyDb:
        _read_only = True

        def __init__(self, db_path: Path) -> None:
            self._path = str(db_path)
            self.released = False
            self.resumed = False

        def execute(self, sql: str) -> None:
            raise AssertionError(f"read-only /forget must not execute SQL directly: {sql}")

        def query(self, sql: str) -> list[dict[str, str]]:
            captured["query"] = sql
            return []

        def release_file_handle_for_external_writer(self) -> None:
            self.released = True

        def resume_readonly_file_handle(self) -> None:
            self.resumed = True

    def fake_enqueue(command: Any, *, db_path: str, user_id: str) -> str:
        captured["command"] = command
        captured["db_path"] = db_path
        captured["user_id"] = user_id
        return command.task_id

    monkeypatch.setattr("duckclaw.db_write_fire_and_forget.enqueue_write_command", fake_enqueue)
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.wait_write_task",
        lambda *_args, **_kwargs: DbWriteTaskStatus(status="success"),
    )
    monkeypatch.setenv("DUCKCLAW_WRITE_POLL_SEC", "30")

    db = ReadOnlyDb(tmp_path / "vault.duckdb")
    result = execute_forget(db, "default", tenant_id="tenant-a")

    command = captured["command"]
    assert result == "✅ Historial borrado."
    assert command.command_type == "forget_chat_state"
    assert command.tenant_id == "tenant-a"
    assert command.actor_email == "chat:default"
    assert command.chat_id == "default"
    assert captured["db_path"] == str((tmp_path / "vault.duckdb").resolve())
    assert captured["user_id"] == "default"
    assert db.released is True
    assert db.resumed is True


def test_forget_fire_and_forget_returns_queued_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReadOnlyDb:
        _read_only = True

        def __init__(self, db_path: Path) -> None:
            self._path = str(db_path)

        def execute(self, sql: str) -> None:
            raise AssertionError(sql)

        def query(self, _sql: str) -> list[dict[str, str]]:
            return []

        def release_file_handle_for_external_writer(self) -> None:
            return None

        def resume_readonly_file_handle(self) -> None:
            return None

    monkeypatch.delenv("DUCKCLAW_WRITE_POLL_SEC", raising=False)
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.enqueue_write_command",
        lambda *_args, **_kwargs: "forget-task-1",
    )

    result = execute_forget(ReadOnlyDb(tmp_path / "vault.duckdb"), "default", tenant_id="tenant-a")
    assert result == "Write encolado (task_id=forget-task-1)"
