"""Playground catalog ACL: visible == list rules; no false 403 on DB blips."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self._read_only = False

    def execute(self, sql: str, params=None):
        if params is None:
            return self._con.execute(sql)
        return self._con.execute(sql, params)

    def fetchone(self):
        return self._con.fetchone()

    def fetchall(self):
        return self._con.fetchall()

    def fetchdf(self):
        return self._con.fetchdf()


def test_get_visible_worker_includes_assignment_and_public(tmp_path: Path) -> None:
    from duckclaw.admin_worker_catalog import (
        create_worker,
        ensure_admin_worker_catalog_schema,
        get_visible_worker_for_actor,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    adapter = _Adapter(con)
    try:
        ensure_profile_for_user(adapter, email="owner@test.local")
        teammate = ensure_profile_for_user(adapter, email="teammate@test.local")
        ensure_admin_worker_catalog_schema(adapter)

        create_worker(
            adapter,
            owner_email="owner@test.local",
            worker_id="public-bot",
            display_name="Public Bot",
            visibility="public",
        )
        # Colleague-owned worker living on teammate's tenant (list/get filter by tenant).
        con.execute(
            "INSERT INTO main.admin_worker_catalog "
            "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, "
            "source_template_id, visibility, active, status) "
            "VALUES (?, ?, ?, ?, ?, 'runtime', 'default', 'private', true, 'active')",
            [
                "wrk_shared1",
                teammate["tenant_id"],
                "owner@test.local",
                "shared-analyst",
                "Shared Analyst",
            ],
        )
        con.execute(
            "INSERT INTO main.admin_worker_assignments "
            "(worker_uid, target_email, target_tenant_id, permission) VALUES (?, ?, ?, ?)",
            ["wrk_shared1", "teammate@test.local", teammate["tenant_id"], "use"],
        )

        assert get_visible_worker_for_actor(
            adapter, actor_email="owner@test.local", worker_id="public-bot"
        )
        assert get_visible_worker_for_actor(
            adapter, actor_email="teammate@test.local", worker_id="shared-analyst"
        )
        # Same tenant public worker owned by someone else.
        con.execute(
            "INSERT INTO main.admin_worker_catalog "
            "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, "
            "source_template_id, visibility, active, status) "
            "VALUES (?, ?, ?, ?, ?, 'runtime', 'default', 'public', true, 'active')",
            [
                "wrk_pub2",
                teammate["tenant_id"],
                "owner@test.local",
                "team-public",
                "Team Public",
            ],
        )
        assert get_visible_worker_for_actor(
            adapter, actor_email="teammate@test.local", worker_id="team-public"
        )
        assert (
            get_visible_worker_for_actor(
                adapter, actor_email="teammate@test.local", worker_id="missing"
            )
            is None
        )
    finally:
        con.close()


def test_resolve_playground_project_scope_does_not_require_owner_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project ACL alone must set catalog_allowed (avoid double-gate false 403)."""
    from routers.admin_domains.playground import chat_turn as mod

    class _CM:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "core.admin_identity.open_gateway_db",
        lambda *, read_only=True: _CM(),
    )

    def _ensure(db, email, **kwargs):
        del db, kwargs
        return {"email": email, "tenant_id": "t1", "telegram_user_id": ""}

    monkeypatch.setattr("core.admin_identity.ensure_profile_for_user", _ensure)
    monkeypatch.setattr("duckclaw.admin_user_profiles.ensure_profile_for_user", _ensure)
    monkeypatch.setattr(
        "core.admin_identity.resolve_playground_worker_for_project",
        lambda db, actor_email, project_id, worker_id: ("team-worker", project_id),
    )
    monkeypatch.setattr(
        "core.admin_identity.project_context_for_actor",
        lambda db, actor_email, project_id: {"project_id": project_id},
    )
    monkeypatch.setattr(
        "core.admin_identity.get_visible_worker_for_actor",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "routers.admin_domains.playground.knowledge_scope_resolution.resolve_playground_knowledge_scope",
        lambda *args, **kwargs: "platform",
    )

    turn = mod.resolve_playground_actor_turn(
        "alice@test.local",
        worker_id="default",
        project_id="prj_x",
        chat_id="admin-conv-x",
    )
    assert turn.catalog_allowed is True
    assert turn.wid == "team-worker"
