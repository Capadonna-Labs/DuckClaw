"""Contrato happy path: login admin → playground config → turno chat (mock LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _mock_playground_team(*, workers: list[str]) -> dict:
    return {
        "authorized": True,
        "team_chat_id": "admin-playground",
        "telegram_user_id": "test-owner",
        "tenant_id": "default",
        "whitelist_role": "owner",
        "team_source": "chat",
        "team_hint": "mock",
        "workers": workers,
    }


def test_onboarding_happy_path_login_config_chat(
    gateway_admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="dev-coder",
            display_name="Dev Coder",
        )
    finally:
        db.close()

    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))

    import routers.admin_domains.playground.chat_turn as playground_chat_turn
    import routers.admin_domains.playground_chat as playground_chat_router

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "smoke-ok", "usage_tokens": {"total": 1}}

    monkeypatch.setattr(
        playground_chat_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["dev-coder"]),
    )
    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)

    login = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.local", "password": "secret123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "admin@test.local"
    assert "session" in login.cookies

    headers = {
        "X-Admin-Key": "test-admin-key",
        "X-Duckclaw-Actor": "admin@test.local",
    }
    config = gateway_admin_client.get("/api/v1/admin/playground/config", headers=headers)
    assert config.status_code == 200
    cfg = config.json()
    assert "llm" in cfg
    assert cfg.get("chat_endpoint") == "/api/v1/admin/playground/chat"

    chat = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers=headers,
        json={"worker_id": "dev-coder", "message": "smoke ping"},
    )
    assert chat.status_code == 200
    data = chat.json()
    assert data.get("ok") is True
    assert data.get("response") == "smoke-ok"
