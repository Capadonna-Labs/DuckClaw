from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_env_config_allows_android_keys() -> None:
    from gateway_import import load_gateway_app

    load_gateway_app()
    from routers.admin_domains import env_config

    assert env_config.is_env_key_allowed("ANDROID_ADB_DEBUG_PORT")
    assert env_config.is_env_key_allowed("ANDROID_ADB_HOST")


def test_env_file_prefers_duckclaw_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from gateway_import import load_gateway_app

    load_gateway_app()
    from routers.admin_domains import env_config

    monorepo = tmp_path / "duckclaw"
    vault = tmp_path / "vault"
    monorepo.mkdir()
    vault.mkdir()
    (monorepo / ".env").write_text("ANDROID_ADB_DEBUG_PORT=11111\n", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_ROOT", str(monorepo))
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(vault))
    assert env_config.env_file() == monorepo / ".env"


def test_android_adb_connect_op_persists_debug_port(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ANDROID_ADB_DEBUG_PORT=39069\n", encoding="utf-8")
    monkeypatch.setenv("DUCKCLAW_ROOT", str(tmp_path))

    import routers.admin_domains.env_config as env_config_module

    monkeypatch.setattr(env_config_module, "env_file", lambda: env_path)

    with patch(
        "duckclaw.mcp_android_adb.android_adb_connect",
        return_value={"ok": False, "stderr": "failed to connect", "env_updated": ["ANDROID_ADB_DEBUG_PORT"]},
    ):
        res = admin_client.post(
            "/api/v1/admin/ops/run",
            headers={"X-Admin-Key": "test-admin-key"},
            json={"op_id": "android_adb_connect", "params": {"debug_port": "42281"}},
        )
    assert res.status_code == 200
    assert "42281" in env_path.read_text(encoding="utf-8")
    body = res.json()
    assert body["ok"] is False
    payload = __import__("json").loads(body["stdout"])
    assert payload.get("env_updated") == ["ANDROID_ADB_DEBUG_PORT"]
