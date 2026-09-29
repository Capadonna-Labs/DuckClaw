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
        _upsert_skill_impl(object(), "radar_watchlist", "Vigilar SNX y WOR", "directive")
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

    out = json.loads(_list_skills_impl(_Db(), "default"))
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

    out = json.loads(_list_skills_impl(_Db(), "default"))
    assert out["ok"] is True


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
    out = json.loads(_deactivate_skill_impl(object(), "radar_watchlist"))
    assert out["ok"] is True
    assert calls[0].name == "radar_watchlist"
