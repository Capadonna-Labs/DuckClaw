from __future__ import annotations

import json
from pathlib import Path

import duckdb


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_profile_tenant_is_stable_and_unique(gateway_db: Path) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        first = ensure_profile_for_user(adapter, email="Alice@Test.Local")
        again = ensure_profile_for_user(adapter, email="alice@test.local")
        other = ensure_profile_for_user(adapter, email="bob@test.local")
    finally:
        con.close()

    assert first["email"] == "alice@test.local"
    assert first["tenant_id"] == again["tenant_id"]
    assert first["tenant_id"] != other["tenant_id"]
    assert first["default_worker_id"] == "default"


def test_profile_stores_telegram_and_channels(gateway_db: Path) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user, update_profile

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ensure_profile_for_user(adapter, email="alice@test.local")
        updated = update_profile(
            adapter,
            email="alice@test.local",
            telegram_user_id="12345",
            channels={"telegram": {"enabled": True, "chat_id": "12345"}},
            default_worker_id="assistant",
        )
    finally:
        con.close()

    assert updated["telegram_user_id"] == "12345"
    assert updated["default_worker_id"] == "assistant"
    channels = json.loads(updated["channels_json"])
    assert channels["telegram"]["enabled"] is True


def test_playground_config_uses_actor_profile_not_spoofed_query(
    gateway_admin_client, gateway_db: Path
) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user, update_profile

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        profile = ensure_profile_for_user(adapter, email="admin@test.local")
        updated = update_profile(
            adapter,
            email="admin@test.local",
            telegram_user_id="12345",
            channels={"telegram": {"enabled": True}},
        )
    finally:
        con.close()

    r = gateway_admin_client.get(
        "/api/v1/admin/playground/config?tenant_id=spoofed&telegram_user_id=99999",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["effective_tenant_id"] == profile["tenant_id"]
    assert data["telegram_user_id"] == updated["telegram_user_id"]
    assert data["authorized"] is True


def test_admin_user_workspace_migration_is_idempotent(gateway_db: Path) -> None:
    import importlib

    migration = importlib.import_module("scripts.migrations.003_admin_user_workspaces")

    con = duckdb.connect(str(gateway_db))
    try:
        migration.apply_migration(con)
        migration.apply_migration(con)
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        con.close()

    assert "admin_user_profiles" in tables
    assert "admin_user_agents" in tables
