"""Tests /comfyui --provider command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from duckclaw.db_write_queue import DbWriteTaskStatus
from duckclaw.graphs.on_the_fly_commands import execute_comfyui_provider


class _MemDb:
    def __init__(self):
        self.store: dict[str, str] = {}

    def query(self, sql: str):
        for k, v in self.store.items():
            if k in sql:
                return json.dumps([{"value": v}])
        return json.dumps([])

    def execute(self, sql: str) -> None:
        if "INSERT" in sql.upper():
            parts = sql.split("VALUES")
            if len(parts) > 1:
                chunk = parts[1]
                if "'" in chunk:
                    vals = [x.strip().strip("'") for x in chunk.split(",")]
                    if len(vals) >= 2:
                        self.store[vals[0]] = vals[1]


def test_comfyui_provider_sets_fal(monkeypatch) -> None:
    monkeypatch.setenv("FAL_KEY", "k")
    db = _MemDb()
    msg = execute_comfyui_provider(db, "chat-x", "--provider fal")
    assert "fal" in msg.lower()


def test_comfyui_provider_with_read_only_handle_queues_typed_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAL_KEY", "k")
    captured: dict[str, Any] = {}

    class ReadOnlyDb:
        _read_only = True

        def __init__(self) -> None:
            self._path = str(tmp_path / "vault.duckdb")
            self.released = False
            self.resumed = False

        def execute(self, sql: str) -> None:
            raise AssertionError(f"read-only /comfyui must not execute SQL directly: {sql}")

        def query(self, _sql: str) -> str:
            return json.dumps([])

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

    db = ReadOnlyDb()
    msg = execute_comfyui_provider(db, "chat-x", "--provider fal")

    command = captured["command"]
    assert "fal" in msg.lower()
    assert command.command_type == "upsert_agent_config_entries"
    assert command.actor_email == "chat:chat-x"
    assert command.entries == {"chat_chat-x_comfyui_provider": "fal"}
    assert captured["db_path"] == str((tmp_path / "vault.duckdb").resolve())
    assert captured["user_id"] == "chat-x"
    assert db.released is True
    assert db.resumed is True