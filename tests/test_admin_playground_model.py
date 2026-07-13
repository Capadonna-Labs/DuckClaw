"""Tests PUT /playground/model (admin UI equivalent to /model provider=…)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_HEADERS = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def gateway_with_agent_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from duckclaw.schema_migrations import run_pending_migrations

    dbf = tmp_path / "gw.duckdb"
    con = duckdb.connect(str(dbf))
    try:
        run_pending_migrations(con)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_config (
                key VARCHAR PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    finally:
        con.close()
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(dbf))
    return dbf


def _apply_typed_command_inline(command: object, *, db_path: str, user_id: str) -> str:
    from duckclaw.write_command_handlers import dispatch_command

    _ = user_id
    con = duckdb.connect(db_path, read_only=False)
    try:
        dispatch_command(con, command.model_dump())
    finally:
        con.close()
    return command.task_id


def test_playground_set_model_provider(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    r = admin_client.put(
        "/api/v1/admin/playground/model",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-test", "provider": "deepseek"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["task_id"]
    assert len(data["task_ids"]) >= 3
    assert data["llm"]["provider"] == "deepseek"
    assert any(c["id"] == "deepseek" and c.get("active") for c in data["catalog"])
    con = duckdb.connect(str(gateway_with_agent_config), read_only=True)
    try:
        runtime_rows = con.execute(
            "SELECT domain, key, value_text FROM main.admin_runtime_settings "
            "WHERE actor_email = 'chat:admin-conv-test' ORDER BY key"
        ).fetchall()
        agent_config_rows = con.execute("SELECT key, value FROM agent_config ORDER BY key").fetchall()
    finally:
        con.close()
    assert ("runtime.session", "llm_provider", "deepseek") in runtime_rows
    assert not any(str(row[0]).startswith("chat_admin-conv-test_llm_") for row in agent_config_rows)


def test_playground_set_model_mlx_provider(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLX_MODEL_ID", "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit")
    monkeypatch.setenv("DUCKCLAW_MLX_HOST", "100.99.72.63")
    monkeypatch.setenv("MLX_PORT", "8080")
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    r = admin_client.put(
        "/api/v1/admin/playground/model",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-mlx", "provider": "mlx"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["llm"]["provider"] == "mlx"
    assert "Qwen2.5-Coder" in (data["llm"]["model"] or "")
    assert any(c["id"] == "mlx" and c.get("active") for c in data["catalog"])


def test_playground_set_model_mlx_rejects_openrouter_slug(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLX_MODEL_ID", "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit")
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    r = admin_client.put(
        "/api/v1/admin/playground/model",
        headers=_HEADERS,
        json={
            "chat_id": "admin-conv-mlx-glm",
            "provider": "mlx",
            "model": "z-ai/glm-5.2",
        },
    )
    assert r.status_code == 200
    assert "Qwen2.5-Coder" in (r.json()["llm"]["model"] or "")
    assert "glm" not in (r.json()["llm"]["model"] or "").lower()


def test_playground_config_reflects_chat_override(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mlx")
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    admin_client.put(
        "/api/v1/admin/playground/model",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-xyz", "provider": "groq"},
    )
    r = admin_client.get(
        "/api/v1/admin/playground/config?chat_id=admin-conv-xyz",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["llm"]["provider"] == "groq"
    assert r.json()["llm"].get("scope") == "chat"


def test_playground_set_vault_per_conversation(
    admin_client: TestClient,
    gateway_with_agent_config: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    vault = tmp_path / "tenant" / "custom.duckdb"
    vault.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect(str(vault)).close()
    rel = str(vault)

    store: dict[str, str] = {}
    zset: dict[str, float] = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_set(key, val, ex=None):
        store[key] = val

    async def mock_zadd(key, mapping):
        zset.update(mapping)

    async def mock_expire(key, ttl):
        pass

    async def mock_zrevrange(key, start, end):
        return sorted(zset.keys(), key=lambda k: zset[k], reverse=True)

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=mock_get)
    redis.set = AsyncMock(side_effect=mock_set)
    redis.zadd = AsyncMock(side_effect=mock_zadd)
    redis.expire = AsyncMock(side_effect=mock_expire)
    redis.zrevrange = AsyncMock(side_effect=mock_zrevrange)
    admin_client.app.state.redis = redis

    r = admin_client.put(
        "/api/v1/admin/playground/vault",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-vault", "vault_db_path": rel},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["vault"]["scope"] == "chat"
    assert rel in (data["vault"]["effective_path"] or data["vault"]["override_path"] or "")

    cfg = admin_client.get(
        "/api/v1/admin/playground/config?chat_id=admin-conv-vault",
        headers=_HEADERS,
    )
    assert cfg.status_code == 200
    assert cfg.json()["vault"]["scope"] == "chat"
