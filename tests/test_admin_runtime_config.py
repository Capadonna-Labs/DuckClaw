from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"}


def test_runtime_vaults_are_scoped_to_authenticated_actor(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    owner_dir = repo_root / "db" / "private" / "owner123"
    other_dir = repo_root / "db" / "private" / "other456"
    owner_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    duckdb.connect(str(owner_dir / "axis.duckdb")).close()
    duckdb.connect(str(other_dir / "hidden.duckdb")).close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")

    response = gateway_admin_client.get(
        "/api/v1/admin/runtime/vaults",
        headers=_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()
    paths = [item["path"] for item in data["vaults"]]
    assert data["vault_user_id"] == "owner123"
    assert any(path.endswith("db/private/owner123/axis.duckdb") for path in paths)
    assert not any("other456" in path for path in paths)


def test_runtime_config_get_returns_global_and_chat_rows(
    admin_client: TestClient,
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / "runtime.duckdb"
    con = duckdb.connect(str(vault_path))
    try:
        con.execute(
            """
            CREATE TABLE agent_config (
                key VARCHAR PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.executemany(
            "INSERT INTO agent_config (key, value) VALUES (?, ?)",
            [
                ("global_mode", "shared"),
                ("chat_chat-a_model", "groq"),
                ("chat_other_model", "hidden"),
            ],
        )
    finally:
        con.close()

    response = admin_client.get(
        "/api/v1/admin/runtime/config",
        headers=_ADMIN_HEADERS,
        params={"vault_path": str(vault_path), "chat_id": "chat-a"},
    )

    assert response.status_code == 200
    rows = {item["full_key"]: item for item in response.json()["rows"]}
    assert rows["global_mode"] == {
        "key": "global_mode",
        "full_key": "global_mode",
        "value": "shared",
        "scope": "global",
    }
    assert rows["chat_chat-a_model"] == {
        "key": "model",
        "full_key": "chat_chat-a_model",
        "value": "groq",
        "scope": "chat",
    }
    assert "chat_other_model" not in rows


def test_patch_runtime_settings_returns_task_id(
    gateway_admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    def fake_enqueue(command: object, *, db_path: str, user_id: str) -> str:
        captured.append(command)
        return "task-runtime-1"

    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)

    response = gateway_admin_client.patch(
        "/api/v1/admin/settings/runtime",
        headers=_ADMIN_HEADERS,
        json={
            "settings": [
                {
                    "domain": "duckdb",
                    "key": "legacy_schemas",
                    "value": "cleanup_schema",
                    "scope": "tenant",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-runtime-1"
    assert response.json()["updated"] == ["duckdb.legacy_schemas"]
    assert captured
