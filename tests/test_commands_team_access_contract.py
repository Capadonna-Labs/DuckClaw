from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from duckclaw.graphs import on_the_fly_commands
from duckclaw.write_commands import UpsertAuthorizedUserCommand


CANONICAL_MODULE = "duckclaw.commands.team_access"
TEAM_ACCESS_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "agents"
    / "src"
    / "duckclaw"
    / "commands"
    / "team_access.py"
)
TEAM_ACCESS_READ_CHECK_EXPORTS = (
    "_ensure_authorized_users_table",
    "_is_gateway_owner_user",
    "_is_team_admin",
    "_get_authorized_role",
    "_list_authorized_users",
    "_team_username_by_user_id",
    "_player_label",
    "_player_label_log",
    "_resolve_team_add_uid_and_username",
    "_dedupe_authorized_users_by_user_id",
)
TEAM_ACCESS_MUTATION_EXPORTS = (
    "_upsert_authorized_user",
    "_delete_authorized_user",
    "_invalidate_whitelist_redis_cache",
    "_team_whitelist_audit_enabled",
    "_audit_team_whitelist_rw",
    "_paths_same_duckdb_file",
    "_try_duckdb_checkpoint_rw",
    "_team_whitelist_db",
    "_authorized_users_rw_connection",
    "execute_team_whitelist",
)
WR_ACCESS_EXPORTS = (
    "register_wr_member",
    "get_wr_context",
    "broadcast_alert",
)
TEAM_ACCESS_EXPORTS = (
    *TEAM_ACCESS_READ_CHECK_EXPORTS,
    *TEAM_ACCESS_MUTATION_EXPORTS,
)


def test_team_access_ownership_lives_outside_graphs() -> None:
    for name in TEAM_ACCESS_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    team_access = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(team_access)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_team_access_imports_remain_compatible() -> None:
    team_access = importlib.import_module(CANONICAL_MODULE)

    for name in TEAM_ACCESS_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(team_access, name)


def test_war_room_team_access_exports_are_not_in_generic_core() -> None:
    team_access = importlib.import_module(CANONICAL_MODULE)

    for name in WR_ACCESS_EXPORTS:
        assert not hasattr(team_access, name)
        assert not hasattr(on_the_fly_commands, name)

    source = TEAM_ACCESS_PATH.read_text(encoding="utf-8")
    assert "war_room_core" not in source
    assert "UpsertWarRoomMemberCommand" not in source
    assert "DeleteWarRoomMemberCommand" not in source
    assert "AppendWarRoomAuditCommand" not in source


def test_normal_team_whitelist_mutations_do_not_use_rw_connection_helper() -> None:
    tree = ast.parse(TEAM_ACCESS_PATH.read_text(encoding="utf-8"))
    execute_fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_team_whitelist"
    )
    called_names = {
        node.func.id
        for node in ast.walk(execute_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "_authorized_users_rw_connection" not in called_names
    assert "_upsert_authorized_user" not in called_names
    assert "_delete_authorized_user" not in called_names
    assert "_try_duckdb_checkpoint_rw" not in called_names


class _ReadOnlyTeamAccessDb:
    def __init__(self, db_path: Path) -> None:
        self._path = str(db_path)
        self._read_only = True
        self.released = 0
        self.resumed = 0

    def execute(self, sql: str) -> None:
        raise AssertionError(f"read-only /team must not execute SQL directly: {sql}")

    def query(self, sql: str) -> str:
        if "SELECT role FROM main.authorized_users" in sql:
            return '[{"role": "admin"}]'
        if "SELECT user_id, username, role FROM main.authorized_users" in sql:
            return '[{"user_id": "1", "username": "admin", "role": "admin"}]'
        return "[]"

    def release_file_handle_for_external_writer(self) -> None:
        self.released += 1

    def resume_readonly_file_handle(self) -> None:
        self.resumed += 1


def test_team_add_with_read_only_handle_queues_typed_command_and_releases_handle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    team_access = importlib.import_module(CANONICAL_MODULE)
    db = _ReadOnlyTeamAccessDb(tmp_path / "gateway.duckdb")
    queued: list[tuple[UpsertAuthorizedUserCommand, str, str]] = []

    def fake_enqueue_typed_command(
        command: Any,
        *,
        db_path: str,
        user_id: str = "default",
        queue_name: str = "duckdb_write_queue",
    ) -> str:
        assert queue_name == "duckdb_write_queue"
        assert isinstance(command, UpsertAuthorizedUserCommand)
        queued.append((command, db_path, user_id))
        return command.task_id

    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue_typed_command)
    monkeypatch.setattr(
        "duckclaw.db_write_queue.poll_task_status_sync",
        lambda _task_id, **_kwargs: SimpleNamespace(status="success", detail=""),
    )

    original_provider = getattr(team_access, "_team_access_acl_db_provider")
    team_access.configure_team_access_acl_db_provider(None)
    try:
        out = team_access.execute_team_whitelist(
            db,
            "tenant-ro",
            "1",
            "--add 2 beta admin",
        )
    finally:
        team_access.configure_team_access_acl_db_provider(original_provider)

    assert out == "✅ Añadido [@beta](tg://user?id=2) (role=admin) al tenant 'tenant-ro'."
    assert len(queued) == 1
    command, target_db_path, user_id = queued[0]
    assert target_db_path == str((tmp_path / "gateway.duckdb").resolve())
    assert user_id == "1"
    assert command.tenant_id == "tenant-ro"
    assert command.actor_email == "telegram:1"
    assert command.user_id == "2"
    assert command.username == "beta"
    assert command.role == "admin"
    assert db.released == 1
    assert db.resumed == 1
