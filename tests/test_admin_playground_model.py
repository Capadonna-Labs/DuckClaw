"""Tests PUT /playground/model (admin UI equivalent to /model provider=…)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_HEADERS = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def gateway_with_agent_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dbf = tmp_path / "gw.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute(
        """
        CREATE TABLE agent_config (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.close()
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", str(dbf))
    return dbf


def test_playground_set_model_provider(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    r = admin_client.put(
        "/api/v1/admin/playground/model",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-test", "provider": "deepseek"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["llm"]["provider"] == "deepseek"
    assert any(c["id"] == "deepseek" and c.get("active") for c in data["catalog"])


def test_playground_config_reflects_chat_override(
    admin_client: TestClient, gateway_with_agent_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mlx")
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
