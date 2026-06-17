from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

from duckclaw.commands import chat_state
from duckclaw.graphs import on_the_fly_commands

CANONICAL_MODULE = "duckclaw.commands.chat_state"
CHAT_STATE_FUNCTION_EXPORTS = (
    "get_chat_state",
    "set_chat_state",
    "_ensure_agent_config",
    "execute_forget",
    "execute_context_toggle",
)


def test_chat_state_ownership_lives_outside_graphs() -> None:
    for name in CHAT_STATE_FUNCTION_EXPORTS:
        assert getattr(chat_state, name).__module__ == CANONICAL_MODULE

    source = inspect.getsource(chat_state)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_chat_state_imports_remain_compatible() -> None:
    assert on_the_fly_commands.get_chat_state is chat_state.get_chat_state
    assert on_the_fly_commands.set_chat_state is chat_state.set_chat_state
    assert on_the_fly_commands._ensure_agent_config is chat_state._ensure_agent_config
    assert on_the_fly_commands._chat_key is chat_state._chat_key
    assert on_the_fly_commands._skip_runtime_ddl is chat_state._skip_runtime_ddl
    assert on_the_fly_commands.execute_forget is chat_state.execute_forget
    assert on_the_fly_commands.execute_context_toggle is chat_state.execute_context_toggle


def test_context_toggle_with_read_only_handle_uses_typed_agent_config_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus

    captured: dict[str, Any] = {}

    class ReadOnlyDb:
        _read_only = True

        def __init__(self, db_path: Path) -> None:
            self._path = str(db_path)
            self.released = False
            self.resumed = False

        def execute(self, sql: str) -> None:
            raise AssertionError(f"read-only /context must not execute SQL directly: {sql}")

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

    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue)
    monkeypatch.setattr(
        "duckclaw.db_write_queue.poll_task_status_sync",
        lambda *_args, **_kwargs: DbWriteTaskStatus(status="success"),
    )

    db = ReadOnlyDb(tmp_path / "vault.duckdb")
    out = chat_state.execute_context_toggle(
        db,
        "chat1",
        "on",
        tenant_id="tenant-a",
    )

    command = captured["command"]
    assert "activado" in out
    assert command.command_type == "upsert_agent_config_entries"
    assert command.tenant_id == "tenant-a"
    assert command.actor_email == "chat:chat1"
    assert command.entries == {"chat_chat1_use_rag": "true"}
    assert captured["db_path"] == str((tmp_path / "vault.duckdb").resolve())
    assert captured["user_id"] == "chat1"
    assert db.released is True
    assert db.resumed is True
