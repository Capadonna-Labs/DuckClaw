from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def _seed_worker(adapter: _Adapter, *, email: str, worker_id: str, display_name: str) -> dict:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import (
        add_worker_version,
        create_worker,
        ensure_admin_worker_catalog_schema,
    )

    ensure_profile_for_user(adapter, email=email)
    ensure_admin_worker_catalog_schema(adapter)
    worker = create_worker(
        adapter,
        owner_email=email,
        worker_id=worker_id,
        display_name=display_name,
    )
    add_worker_version(
        adapter,
        worker_uid=worker["worker_uid"],
        created_by=email,
        manifest_snapshot={"id": worker_id, "name": display_name},
        files_snapshot={"system_prompt.md": f"Prompt for {worker_id}"},
        change_note="seed",
    )
    adapter.execute(
        "INSERT INTO main.admin_user_agents "
        "(tenant_id, owner_email, worker_id, display_name, source_template_id, manifest_path, active) "
        "VALUES (?, ?, ?, ?, 'default', ?, true)",
        [
            worker["tenant_id"],
            email,
            worker_id,
            display_name,
            f"db://admin_worker_catalog/{worker['worker_uid']}/manifest.json",
        ],
    )
    adapter.execute(
        "INSERT INTO main.admin_conversations "
        "(conversation_id, tenant_id, actor_email, title, worker_id, last_worker_id, preferred_worker_id) "
        "VALUES (?, ?, ?, 'Chat', ?, ?, ?)",
        [
            f"sess-{worker_id}",
            worker["tenant_id"],
            email,
            worker_id,
            worker_id,
            worker_id,
        ],
    )
    adapter.execute(
        "UPDATE main.admin_user_profiles SET default_worker_id = ? WHERE email = ?",
        [worker_id, email],
    )
    from duckclaw.catalog_prompt_sync import sync_worker_system_prompt_policy

    sync_worker_system_prompt_policy(
        adapter,
        worker_id=worker_id,
        files={"system_prompt.md": f"Prompt for {worker_id}"},
        actor_email=email,
        worker_uid=worker["worker_uid"],
        force=True,
    )
    return worker


def test_rename_catalog_worker_ok(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import get_latest_worker_version, get_worker_by_uid
    from duckclaw.write_handlers.workers import _apply_rename_catalog_worker

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        worker = _seed_worker(
            adapter,
            email="alice@test.local",
            worker_id="old-agent",
            display_name="Old Agent",
        )
        worker_uid = worker["worker_uid"]
        tenant_id = worker["tenant_id"]

        _apply_rename_catalog_worker(
            adapter,
            {
                "actor_email": "alice@test.local",
                "tenant_id": tenant_id,
                "worker_id": "old-agent",
                "new_worker_id": "new-agent",
            },
        )

        renamed = get_worker_by_uid(adapter, worker_uid)
        assert renamed is not None
        assert renamed["worker_id"] == "new-agent"
        assert renamed["worker_uid"] == worker_uid

        ua = con.execute(
            "SELECT worker_id FROM main.admin_user_agents WHERE tenant_id = ? AND worker_id = ?",
            [tenant_id, "new-agent"],
        ).fetchone()
        assert ua is not None

        conv = con.execute(
            "SELECT worker_id, last_worker_id, preferred_worker_id "
            "FROM main.admin_conversations WHERE conversation_id = ?",
            ["sess-old-agent"],
        ).fetchone()
        assert conv == ("new-agent", "new-agent", "new-agent")

        profile = con.execute(
            "SELECT default_worker_id FROM main.admin_user_profiles WHERE email = ?",
            ["alice@test.local"],
        ).fetchone()
        assert profile[0] == "new-agent"

        latest = get_latest_worker_version(adapter, worker_uid=worker_uid) or {}
        assert (latest.get("manifest_snapshot") or {}).get("id") == "new-agent"

        old_policy = con.execute(
            "SELECT 1 FROM main.prompt_policy_registry "
            "WHERE policy_type = 'system_prompt' AND policy_name = 'old-agent' AND active = true"
        ).fetchone()
        assert old_policy is None
        new_policy = con.execute(
            "SELECT content FROM main.prompt_policy_registry "
            "WHERE policy_type = 'system_prompt' AND policy_name = 'new-agent' "
            "AND active = true AND status = 'active' ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert new_policy is not None
        assert "Prompt for old-agent" in str(new_policy[0])
    finally:
        con.close()


def test_rename_catalog_worker_conflict(gateway_db: Path) -> None:
    from duckclaw.write_handlers.workers import _apply_rename_catalog_worker

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        first = _seed_worker(
            adapter,
            email="alice@test.local",
            worker_id="agent-a",
            display_name="Agent A",
        )
        _seed_worker(
            adapter,
            email="alice@test.local",
            worker_id="agent-b",
            display_name="Agent B",
        )

        with pytest.raises(ValueError, match="ya existe"):
            _apply_rename_catalog_worker(
                adapter,
                {
                    "actor_email": "alice@test.local",
                    "tenant_id": first["tenant_id"],
                    "worker_id": "agent-a",
                    "new_worker_id": "agent-b",
                },
            )
    finally:
        con.close()


def test_rename_catalog_worker_not_visible(gateway_db: Path) -> None:
    from duckclaw.write_handlers.workers import _apply_rename_catalog_worker

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        with pytest.raises(ValueError, match="not visible"):
            _apply_rename_catalog_worker(
                adapter,
                {
                    "actor_email": "alice@test.local",
                    "tenant_id": "default",
                    "worker_id": "missing-agent",
                    "new_worker_id": "renamed-agent",
                },
            )
    finally:
        con.close()
