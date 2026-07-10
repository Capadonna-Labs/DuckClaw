"""Tests PUT /playground/slm and SLM block in /playground/config."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

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
    finally:
        con.close()
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(dbf))
    monkeypatch.setenv("DUCKCLAW_SLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("MLX_MODEL_ID", "gemma4-test")
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


def test_playground_config_includes_slm_block(
    admin_client: TestClient,
    gateway_with_agent_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "routers.admin_domains.playground.slm_settings.probe_mlx_inference_status",
        AsyncMock(return_value="online"),
    )
    r = admin_client.get(
        "/api/v1/admin/playground/config?chat_id=admin-slm-test",
        headers=_HEADERS,
    )
    assert r.status_code == 200
    slm = r.json().get("slm")
    assert isinstance(slm, dict)
    assert slm.get("pm2_name") == "MLX-Inference"
    assert slm.get("model") == "gemma4-test"
    assert slm.get("mlx_status") == "online"
    assert slm.get("enabled") is False


def test_playground_set_slm_enable(
    admin_client: TestClient,
    gateway_with_agent_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "routers.admin_domains.playground.slm_settings.probe_mlx_inference_status",
        AsyncMock(return_value="offline"),
    )
    r = admin_client.put(
        "/api/v1/admin/playground/slm",
        headers=_HEADERS,
        json={
            "chat_id": "admin-slm-conv",
            "enabled": True,
            "adapter_path": "packages/agents/train/gemma4/adapters_lora_yaml",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["slm"]["enabled"] is True
    assert data["slm"]["mlx_status"] == "offline"

    con = duckdb.connect(str(gateway_with_agent_config), read_only=True)
    try:
        rows = con.execute(
            "SELECT key, value_text FROM main.admin_runtime_settings "
            "WHERE actor_email = 'chat:admin-slm-conv' ORDER BY key"
        ).fetchall()
    finally:
        con.close()
    keys = {row[0]: row[1] for row in rows}
    assert keys.get("slm_enabled") == "true"
    assert "adapters_lora_yaml" in (keys.get("slm_adapter_path") or "")


def test_playground_set_slm_disable(
    admin_client: TestClient,
    gateway_with_agent_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "routers.admin_domains.playground.slm_settings.probe_mlx_inference_status",
        AsyncMock(return_value="unknown"),
    )
    admin_client.put(
        "/api/v1/admin/playground/slm",
        headers=_HEADERS,
        json={"chat_id": "admin-slm-off", "enabled": True},
    )
    r = admin_client.put(
        "/api/v1/admin/playground/slm",
        headers=_HEADERS,
        json={"chat_id": "admin-slm-off", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["slm"]["enabled"] is False
