from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from duckclaw.graphs import on_the_fly_commands
from duckclaw.write_commands import UpsertAgentConfigEntriesCommand


CANONICAL_MODULE = "duckclaw.commands.team_templates"
TEAM_TEMPLATE_EXPORTS = (
    "_tenant_team_config_key",
    "get_team_templates",
    "set_team_templates",
    "get_tenant_team_templates",
    "set_tenant_team_templates",
    "_canonicalize_team_template_ids",
    "get_effective_team_templates",
    "_resolve_template_id",
    "execute_team",
)


def test_team_templates_ownership_lives_outside_graphs() -> None:
    for name in TEAM_TEMPLATE_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    team_templates = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(team_templates)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_team_template_imports_remain_compatible() -> None:
    team_templates = importlib.import_module(CANONICAL_MODULE)

    for name in TEAM_TEMPLATE_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(team_templates, name)


class _ReadOnlyTeamDb:
    def __init__(self, db_path: Path, *, initial_team: list[str] | None = None) -> None:
        self._path = str(db_path)
        self._read_only = True
        self.initial_team = list(initial_team or [])
        self.released = 0
        self.resumed = 0

    def execute(self, _sql: str) -> None:
        raise AssertionError("read-only /workers must not execute direct writes")

    def query(self, sql: str) -> str:
        if "team_templates" not in sql or not self.initial_team:
            return "[]"
        return json.dumps([{"value": json.dumps(self.initial_team)}])

    def release_file_handle_for_external_writer(self) -> None:
        self.released += 1

    def resume_readonly_file_handle(self) -> None:
        self.resumed += 1


def test_workers_read_only_set_queues_typed_chat_team_command(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.commands import team_templates
    from duckclaw.commands.chat_state import _chat_key

    queued: list[tuple[UpsertAgentConfigEntriesCommand, str, str]] = []

    def fake_enqueue_typed_command(
        command: Any,
        *,
        db_path: str,
        user_id: str = "default",
        queue_name: str = "duckdb_write_queue",
    ) -> str:
        assert queue_name == "duckdb_write_queue"
        assert isinstance(command, UpsertAgentConfigEntriesCommand)
        queued.append((command, db_path, user_id))
        return command.task_id

    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda *_args, **_kwargs: ["alpha", "beta"])
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.enqueue_typed_command",
        fake_enqueue_typed_command,
    )
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.poll_task_status_sync",
        lambda _task_id, timeout_sec=30.0: SimpleNamespace(status="success", detail=""),
    )

    db_path = tmp_path / "vault.duckdb"
    db = _ReadOnlyTeamDb(db_path)

    out = team_templates.execute_team(
        db,
        "chat-ro",
        "alpha",
        tenant_id="tenant-ro",
        requester_id="requester-ro",
    )

    assert out == "✅ Equipo de este chat: alpha. El manager delegará solo a estos."
    assert len(queued) == 1
    command, target_db_path, user_id = queued[0]
    assert target_db_path == str(db_path.resolve())
    assert user_id == "chat-ro"
    assert command.tenant_id == "tenant-ro"
    assert command.actor_email == "chat:chat-ro"
    assert command.entries == {_chat_key("chat-ro", "team_templates")[:128]: '["alpha"]'}
    assert db.released == 1
    assert db.resumed == 1


def test_workers_read_only_admin_sync_queues_typed_tenant_team_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from duckclaw.commands import team_templates

    queued: list[UpsertAgentConfigEntriesCommand] = []

    def fake_enqueue_typed_command(
        command: Any,
        *,
        db_path: str,
        user_id: str = "default",
        queue_name: str = "duckdb_write_queue",
    ) -> str:
        _ = db_path, user_id, queue_name
        assert isinstance(command, UpsertAgentConfigEntriesCommand)
        queued.append(command)
        return command.task_id

    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda *_args, **_kwargs: ["alpha", "beta"])
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.enqueue_typed_command",
        fake_enqueue_typed_command,
    )
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.poll_task_status_sync",
        lambda _task_id, timeout_sec=30.0: SimpleNamespace(status="success", detail=""),
    )

    original_checker = getattr(team_templates, "_team_admin_checker")
    team_templates.configure_team_template_admin_checker(
        lambda _db, *, tenant_id, requester_id: tenant_id == "tenant-ro" and requester_id == "admin-ro"
    )
    try:
        out = team_templates.execute_team(
            _ReadOnlyTeamDb(tmp_path / "vault.duckdb"),
            "chat-ro",
            "alpha",
            tenant_id="tenant-ro",
            requester_id="admin-ro",
        )
    finally:
        team_templates.configure_team_template_admin_checker(original_checker)

    assert out == "✅ Equipo de este chat: alpha. El manager delegará solo a estos."
    assert [command.entries for command in queued] == [
        {"chat_chat-ro_team_templates": '["alpha"]'},
        {"tenant_team:tenant-ro": '["alpha"]'},
    ]


def test_workers_read_only_add_and_rm_queue_typed_chat_team_commands(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from duckclaw.commands import team_templates
    from duckclaw.commands.chat_state import _chat_key

    queued: list[UpsertAgentConfigEntriesCommand] = []

    def fake_enqueue_typed_command(
        command: Any,
        *,
        db_path: str,
        user_id: str = "default",
        queue_name: str = "duckdb_write_queue",
    ) -> str:
        _ = db_path, user_id, queue_name
        assert isinstance(command, UpsertAgentConfigEntriesCommand)
        queued.append(command)
        return command.task_id

    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda *_args, **_kwargs: ["alpha", "beta"])
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.enqueue_typed_command",
        fake_enqueue_typed_command,
    )
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.poll_task_status_sync",
        lambda _task_id, timeout_sec=30.0: SimpleNamespace(status="success", detail=""),
    )

    add_out = team_templates.execute_team(
        _ReadOnlyTeamDb(tmp_path / "add.duckdb", initial_team=["alpha"]),
        "chat-ro",
        "--add beta",
        tenant_id="tenant-ro",
    )
    rm_out = team_templates.execute_team(
        _ReadOnlyTeamDb(tmp_path / "rm.duckdb", initial_team=["alpha", "beta"]),
        "chat-ro",
        "--rm beta",
        tenant_id="tenant-ro",
    )

    assert add_out == "✅ Añadidos al equipo: beta. Equipo: alpha, beta."
    assert rm_out == "✅ Quitado beta del equipo. Quedan: alpha."
    key = _chat_key("chat-ro", "team_templates")[:128]
    assert [command.entries for command in queued] == [
        {key: '["alpha", "beta"]'},
        {key: '["alpha"]'},
    ]
