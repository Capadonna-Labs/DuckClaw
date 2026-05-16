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


def test_telegram_whitelist_get(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/telegram/whitelist?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("tenant_id") == "default"
    assert "users" in data
