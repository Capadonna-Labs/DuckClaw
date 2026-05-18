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
