from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi.testclient import TestClient


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def _apply_typed_command_inline(command: object, *, db_path: str, user_id: str) -> str:
    from duckclaw.write_command_handlers import dispatch_command

    _ = user_id
    con = duckdb.connect(db_path, read_only=False)
    try:
        dispatch_command(con, command.model_dump())
    finally:
        con.close()
    return command.task_id


def test_runtime_settings_precedence_masking_and_bootstrap(
    gateway_db: Path,
    monkeypatch,
) -> None:
    from duckclaw.admin_runtime_settings import (
        list_runtime_settings_effective,
        resolve_runtime_setting,
        upsert_runtime_setting,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.bootstrap_core import bootstrap_core_schema

    monkeypatch.setenv("DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS", "env_schema")

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="alice@test.local")

        assert (
            resolve_runtime_setting(
                adapter,
                tenant_id=profile["tenant_id"],
                actor_email="alice@test.local",
                domain="duckdb",
                key="legacy_schemas",
                env_key="DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS",
                default="",
            )["value"]
            == "env_schema"
        )

        upsert_runtime_setting(
            adapter,
            tenant_id="global",
            actor_email="",
            domain="duckdb",
            key="legacy_schemas",
            value_text="global_schema",
            updated_by="admin@test.local",
        )
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="",
            domain="duckdb",
            key="legacy_schemas",
            value_text="tenant_schema",
            updated_by="admin@test.local",
        )
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="alice@test.local",
            domain="duckdb",
            key="legacy_schemas",
            value_text="actor_schema",
            updated_by="alice@test.local",
        )
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="alice@test.local",
            domain="telegram",
            key="bot_token",
            value_text="super-secret-token",
            value_kind="secret",
            secret=True,
            updated_by="alice@test.local",
        )

        resolved = resolve_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="alice@test.local",
            domain="duckdb",
            key="legacy_schemas",
            env_key="DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS",
            default="",
        )
        settings = list_runtime_settings_effective(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="alice@test.local",
            domains=["duckdb", "telegram"],
        )
    finally:
        con.close()

    assert resolved["value"] == "actor_schema"
    by_key = {(item["domain"], item["key"]): item for item in settings}
    assert by_key[("duckdb", "legacy_schemas")]["value_text"] == "actor_schema"
    assert by_key[("duckdb", "legacy_schemas")]["source"] == "db"
    assert by_key[("telegram", "bot_token")]["configured"] is True
    assert by_key[("telegram", "bot_token")]["masked_value"] == "********"
    assert "super-secret-token" not in str(by_key[("telegram", "bot_token")])


def test_gateway_runtime_settings_patch_is_db_first_masked_and_audited(
    gateway_admin_client: TestClient,
    gateway_db: Path,
    monkeypatch,
) -> None:
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)

    patched = gateway_admin_client.patch(
        "/api/v1/admin/settings/runtime",
        headers=headers,
        json={
            "settings": [
                {
                    "domain": "duckdb",
                    "key": "legacy_schemas",
                    "value": "db_first_schema",
                    "scope": "actor",
                },
                {
                    "domain": "telegram",
                    "key": "bot_token",
                    "value": "token-from-ui",
                    "scope": "actor",
                    "secret": True,
                },
            ]
        },
    )
    assert patched.status_code == 200
    assert patched.json()["updated"] == ["duckdb.legacy_schemas", "telegram.bot_token"]
    assert patched.json()["task_id"]
    assert len(patched.json()["task_ids"]) == 2

    listed = gateway_admin_client.get(
        "/api/v1/admin/settings/runtime?domain=duckdb&domain=telegram",
        headers=headers,
    )
    assert listed.status_code == 200
    settings = {(item["domain"], item["key"]): item for item in listed.json()["settings"]}
    assert settings[("duckdb", "legacy_schemas")]["value_text"] == "db_first_schema"
    assert settings[("telegram", "bot_token")]["masked_value"] == "********"
    assert "token-from-ui" not in listed.text


def test_playground_config_uses_actor_runtime_defaults(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DUCKCLAW_RUNTIME_AGENTS_DIR", str(tmp_path / "runtime-agents"))
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    vault_path = tmp_path / "axis.duckdb"
    duckdb.connect(str(vault_path)).close()
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    created = gateway_admin_client.post(
        "/api/v1/admin/user-agents",
        headers=headers,
        json={
            "worker_id": "axis_bot",
            "display_name": "AXIS Bot",
            "source_template_id": "default",
        },
    )
    assert created.status_code == 200

    patched = gateway_admin_client.patch(
        "/api/v1/admin/settings/runtime",
        headers=headers,
        json={
            "settings": [
                {"domain": "llm", "key": "provider", "value": "groq", "scope": "actor"},
                {"domain": "llm", "key": "model", "value": "llama-3.3-70b", "scope": "actor"},
                {
                    "domain": "llm",
                    "key": "base_url",
                    "value": "https://api.groq.com/openai/v1",
                    "scope": "actor",
                },
                {
                    "domain": "playground",
                    "key": "default_worker_id",
                    "value": "axis_bot",
                    "scope": "actor",
                },
                {
                    "domain": "playground",
                    "key": "default_vault_db_path",
                    "value": str(vault_path),
                    "scope": "actor",
                },
            ]
        },
    )
    assert patched.status_code == 200

    cfg = gateway_admin_client.get("/api/v1/admin/playground/config", headers=headers)
    assert cfg.status_code == 200
    body = cfg.json()
    assert body["llm"] == {
        "provider": "groq",
        "model": "llama-3.3-70b",
        "base_url": "https://api.groq.com/openai/v1",
        "scope": "runtime",
    }
    assert body["selected_worker_id"] == "axis_bot"
    assert body["vault"]["effective_path"] == str(vault_path)
    assert body["vault"]["scope"] == "runtime"
