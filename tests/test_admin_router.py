"""Tests Admin API router (spec: DuckClaw_Admin_UI)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    import sys

    gw_dir = repo / "services" / "api-gateway"
    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    from main import app as gateway_app

    return TestClient(gateway_app)


def test_admin_requires_key(admin_client: TestClient):
    r = admin_client.get("/api/v1/admin/health")
    assert r.status_code == 401


def test_admin_health_ok(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/health",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "workers_count" in data


def test_list_templates(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    assert "templates" in r.json()


def test_fly_commands(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/fly-commands",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "commands" in data
    assert isinstance(data["commands"], list)
    assert any(c.get("cmd") == "/team" for c in data["commands"])


def test_admin_audit_empty(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/audit",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    assert "entries" in r.json()


def test_catalog_skills(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "global" in data
    assert "template_local" in data


def test_playground_config(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/playground/config",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "llm" in data
    assert "catalog" in data
    assert "workers" in data
    assert isinstance(data.get("workers"), list)
    assert "authorized" in data
    assert "team_chat_id" in data
    assert data.get("chat_endpoint") == "/api/v1/admin/playground/chat"


def test_playground_config_team_for_telegram_chat(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import list_workers

    all_w = list_workers()
    if not all_w:
        pytest.skip("need templates")
    target = all_w[0]
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "7822026745")
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "pg_team.duckdb")
        db = DuckClaw(db_path, read_only=False, engine="python")
        from duckclaw.graphs.on_the_fly_commands import set_team_templates

        set_team_templates(db, "7822026745", [target])
        db.close()
        monkeypatch.setenv("DUCKDB_PATH", db_path)
        r = admin_client.get(
            "/api/v1/admin/playground/config",
            headers={"X-Admin-Key": "test-admin-key"},
            params={"telegram_user_id": "7822026745", "tenant_id": "default"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("authorized") is True
    assert target in (data.get("workers") or [])
    assert data.get("team_source") == "chat"


def _mock_playground_team(*, workers: list[str], authorized: bool = True) -> dict:
    return {
        "workers": workers,
        "authorized": authorized,
        "team_chat_id": "admin-playground",
        "telegram_user_id": "test-owner",
        "tenant_id": "default",
        "whitelist_role": "owner",
        "team_source": "chat",
        "team_hint": "mock",
    }


def test_playground_chat(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    import routers.admin as admin_router

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "respuesta-mock", "usage_tokens": {"total": 1}}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["AXIS-Maestro"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "AXIS-Maestro", "message": "hola"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("response") == "respuesta-mock"
    assert data.get("worker_id") == "AXIS-Maestro"


def test_playground_chat_rejects_worker_outside_team(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["finanz"]),
    )
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "AXIS-Maestro", "message": "hola"},
    )
    assert r.status_code == 403


def test_playground_chat_no_tailscale_key(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DUCKCLAW_TAILSCALE_AUTH_KEY", "ts-required")
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    import routers.admin as admin_router

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "ok"}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "default", "message": "ping"},
    )
    assert r.status_code == 200
    assert r.json().get("response") == "ok"


def test_catalog_topologies(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/topologies",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    ids = [t["id"] for t in r.json().get("topologies") or []]
    assert "general" in ids
    assert "axis_orchestrator" in ids


def test_catalog_mcp(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/mcp",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "duckclaw_mcp" in data
    assert "tools" in data["duckclaw_mcp"]
    assert "live" in data["duckclaw_mcp"]


def test_ops_commands(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/ops/commands",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    cmds = r.json().get("commands") or []
    assert any(c.get("id") == "pm2_list" for c in cmds)


def test_telegram_whitelist_get(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/telegram/whitelist?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("tenant_id") == "default"
    assert "users" in data


def test_telegram_whitelist_resolves_gateway_tenant(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """default en UI → tenant efectivo del gateway (p. ej. Marco vía DUCKCLAW_GATEWAY_TENANT_ID)."""
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "Marco")
    dbf = tmp_path / "hub.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    import duckdb

    con = duckdb.connect(str(dbf))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS main.authorized_users (
            tenant_id VARCHAR, user_id VARCHAR, username VARCHAR,
            role VARCHAR DEFAULT 'user', added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        );
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES ('default', '111', 'legacy', 'user');
        """
    )
    con.close()

    r = admin_client.get(
        "/api/v1/admin/telegram/whitelist?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("effective_tenant_id") == "Marco"
    assert data.get("tenant_id") == "Marco"
    ids = [u["user_id"] for u in data.get("users") or []]
    assert "111" in ids

    r2 = admin_client.post(
        "/api/v1/admin/telegram/whitelist",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"tenant_id": "default", "user_id": "7822026745", "username": "Owner", "role": "admin"},
    )
    assert r2.status_code == 200
    assert r2.json().get("tenant_id") == "Marco"

    con = duckdb.connect(str(dbf))
    row = con.execute(
        "SELECT tenant_id FROM main.authorized_users WHERE user_id='7822026745'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "Marco"
