from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

from duckclaw.graphs import on_the_fly_commands


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
