"""Tests for the skills_management forge skill (create/edit/list/deactivate)."""

from __future__ import annotations

import json

from duckclaw.forge.skills.skills_management_bridge import (
    _deactivate_skill_impl,
    _list_skills_impl,
    _upsert_skill_impl,
    register_skills_management_skill,
)


def test_register_skills_management_skill_adds_all_four_tools() -> None:
    tools: list = []
    register_skills_management_skill(tools, {}, db=None)
    names = {getattr(t, "name", "") for t in tools}
    assert names == {"create_skill", "edit_skill", "list_skills", "deactivate_skill"}


def test_register_skips_tools_already_present() -> None:
    class _Existing:
        name = "create_skill"

    tools: list = [_Existing()]
    register_skills_management_skill(tools, {}, db=None)
    names = [getattr(t, "name", "") for t in tools]
    assert names.count("create_skill") == 1
    assert "list_skills" in names


def test_create_skill_directive_dispatches_upsert_command(monkeypatch) -> None:
    calls: list = []

    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/vault.duckdb"),
    )

    def _fake_dispatch(db, command, *, actor, db_path):
        calls.append((command, actor, db_path))
        return True, ""

    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._dispatch_skill_command",
        _fake_dispatch,
    )

    out = json.loads(
        _upsert_skill_impl(
            object(), "radar_watchlist", "Vigilar SNX y WOR", "directive", "user-juan-tenant"
        )
    )

    assert out["ok"] is True
    assert out["name"] == "radar_watchlist"
    assert "/radar_watchlist" in out["message"]
    assert len(calls) == 1
    command, actor, db_path = calls[0]
    assert command.name == "radar_watchlist"
    assert command.skill_type == "directive"
    assert command.implementation_ref == "directive://radar_watchlist"
    assert command.description == "Vigilar SNX y WOR"
    # Regression: tenant_id used to be left at the Pydantic default ("default")
    # instead of the caller's real tenant, so DB-Writer rejected every write
    # with "Tenant mismatch for actor" — silently, since dispatch always
    # reported ok=True anyway (see test_dispatch_skill_command_* below).
    assert command.tenant_id == "user-juan-tenant"
    assert actor == "juan@example.com"
    assert db_path == "/tmp/vault.duckdb"


def test_create_skill_python_notes_metadata_only_limitation(monkeypatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/vault.duckdb"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._dispatch_skill_command",
        lambda db, command, *, actor, db_path: (True, ""),
    )

    out = json.loads(_upsert_skill_impl(object(), "some_tool", "desc", "python"))
    assert out["ok"] is True
    assert "no crea una tool ejecutable" in out["message"]


def test_upsert_skill_rejects_empty_name_or_description() -> None:
    assert json.loads(_upsert_skill_impl(object(), "", "desc"))["ok"] is False
    assert json.loads(_upsert_skill_impl(object(), "name", ""))["ok"] is False


def test_upsert_skill_reports_dispatch_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/vault.duckdb"),
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._dispatch_skill_command",
        lambda db, command, *, actor, db_path: (False, "Catalog skill name already exists: radar_watchlist"),
    )
    out = json.loads(_upsert_skill_impl(object(), "radar_watchlist", "desc"))
    assert out["ok"] is False
    assert "already exists" in out["error"]


def test_list_skills_queries_admin_skills_scoped_to_tenant_and_actor(monkeypatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/vault.duckdb"),
    )

    class _Db:
        def query(self, sql: str) -> str:
            assert "admin_skills" in sql
            assert "tenant_id = 'default'" in sql
            assert "owner_email = 'juan@example.com'" in sql
            return json.dumps([{"name": "radar_watchlist", "skill_type": "directive"}])

    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._open_hub_read_only",
        lambda path: _Db(),
    )
    out = json.loads(_list_skills_impl(object(), "default"))
    assert out["ok"] is True
    assert out["skills"] == [{"name": "radar_watchlist", "skill_type": "directive"}]


def test_list_skills_escapes_single_quotes_in_actor_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("o'brien@example.com", "/tmp/vault.duckdb"),
    )

    class _Db:
        def query(self, sql: str) -> str:
            assert "o''brien@example.com" in sql
            return json.dumps([])

    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._open_hub_read_only",
        lambda path: _Db(),
    )
    out = json.loads(_list_skills_impl(object(), "default"))
    assert out["ok"] is True


def test_skills_target_gateway_hub_not_worker_vault(monkeypatch) -> None:
    """Regression: resolving the path from the worker's bound db (its vault)
    made create_skill write — and list_skills read — admin_skills in the
    vault, while the "/" menu and /name invocation read the hub. The skill
    looked saved to the agent but never showed up anywhere else."""
    from duckclaw.forge.skills.skills_management_bridge import _actor_and_db_path

    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path", lambda: "/data/hub/duckclaw.duckdb"
    )

    class _VaultDb:
        _path = "/data/private/1/quant_traderdb1.duckdb"

    _, path = _actor_and_db_path(_VaultDb())
    assert path == "/data/hub/duckclaw.duckdb"


def test_deactivate_skill_dispatches_deactivate_command(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/vault.duckdb"),
    )

    def _fake_dispatch(db, command, *, actor, db_path):
        calls.append(command)
        return True, ""

    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._dispatch_skill_command",
        _fake_dispatch,
    )
    out = json.loads(_deactivate_skill_impl(object(), "radar_watchlist", "user-juan-tenant"))
    assert out["ok"] is True
    assert calls[0].name == "radar_watchlist"
    assert calls[0].tenant_id == "user-juan-tenant"


def test_dispatch_skill_command_reports_db_writer_failure(monkeypatch) -> None:
    """Regression: DB-Writer rejecting a command (e.g. tenant mismatch) must
    surface as ok=False, not get swallowed into a blind ok=True."""
    from duckclaw.forge.skills.skills_management_bridge import _dispatch_skill_command
    from duckclaw.db_write_queue import DbWriteTaskStatus

    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.enqueue_write_command",
        lambda command, db_path, user_id: "task-123",
    )
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.wait_write_task",
        lambda task_id, timeout_sec: DbWriteTaskStatus(
            status="failed", detail="Tenant mismatch for actor: juan@example.com"
        ),
    )

    ok, err = _dispatch_skill_command(
        object(), object(), actor="juan@example.com", db_path="/tmp/vault.duckdb"
    )
    assert ok is False
    assert "Tenant mismatch" in err


def test_dispatch_skill_command_never_claims_success_on_timeout(monkeypatch) -> None:
    """Regression: this deployment runs DUCKCLAW_WRITE_POLL_SEC=0 (fire-and-
    forget), under which enqueue_write_and_resolve() would report ok=True the
    instant a command is enqueued, regardless of what DB-Writer does with it
    afterward. _dispatch_skill_command must not inherit that blind-success
    behavior — no status within its own timeout must be ok=False."""
    from duckclaw.forge.skills.skills_management_bridge import _dispatch_skill_command

    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.enqueue_write_command",
        lambda command, db_path, user_id: "task-456",
    )
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.wait_write_task",
        lambda task_id, timeout_sec: None,
    )

    ok, err = _dispatch_skill_command(
        object(), object(), actor="juan@example.com", db_path="/tmp/vault.duckdb"
    )
    assert ok is False
    assert "task-456" in err


def test_list_skills_fits_the_tool_output_cap_with_many_long_directives(monkeypatch) -> None:
    """Full 1 KB directive texts pushed the listing past the 8 KB pruning cap and the
    alphabetical tail (newest skills) vanished; the agent then reported them as unsaved."""
    monkeypatch.setattr(
        "duckclaw.forge.skills.skills_management_bridge._actor_and_db_path",
        lambda db: ("juan@example.com", "/tmp/hub.duckdb"),
    )
    rows = [{"name": f"skill_{i:02d}", "skill_type": "directive", "description": "x" * 1024} for i in range(15)]

    class _Db:
        def query(self, sql: str) -> str:
            return json.dumps(rows)

    monkeypatch.setattr("duckclaw.forge.skills.skills_management_bridge._open_hub_read_only", lambda path: _Db())
    raw = _list_skills_impl(object(), "default")
    out = json.loads(raw)
    assert len(raw) < 8000
    assert out["count"] == 15 and out["skills"][-1]["name"] == "skill_14"
