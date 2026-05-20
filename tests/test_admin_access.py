"""Tests Admin Access API (console users, login, shared grants)."""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from duckclaw.admin_console_users import (
    authenticate_console_user,
    ensure_admin_console_users_table,
    hash_password,
    seed_admin_console_users_if_empty,
    upsert_console_user,
    verify_password,
)
from duckclaw.shared_db_grants import ensure_user_shared_db_access_table


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


@pytest.fixture
def gateway_admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    return TestClient(load_gateway_app())


@pytest.fixture
def gateway_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS

    p = tmp_path / "gateway.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(p))
    con = duckdb.connect(str(p))
    try:
        adapter = _Adapter(con)
        ensure_admin_console_users_table(adapter)
        ensure_user_shared_db_access_table(adapter)
        upsert_console_user(
            adapter,
            email="admin@test.local",
            nombre="Admin Test",
            rol="admin",
            password="secret123",
            initials="AT",
        )
    finally:
        con.close()
    return p


def test_password_hash_roundtrip() -> None:
    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)


def test_authenticate_console_user(gateway_db: Path) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ok = authenticate_console_user(adapter, email="admin@test.local", password="secret123")
        assert ok is not None
        assert ok["rol"] == "admin"
        bad = authenticate_console_user(adapter, email="admin@test.local", password="nope")
        assert bad is None
    finally:
        con.close()


def test_seed_idempotent(gateway_db: Path) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        n1 = seed_admin_console_users_if_empty(adapter)
        n2 = seed_admin_console_users_if_empty(adapter)
        assert n1 == 0
        assert n2 == 0
    finally:
        con.close()


def test_admin_login_ok(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    r = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.local", "password": "secret123"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@test.local"
    assert data["rol"] == "admin"


def test_admin_login_fail(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    r = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.local", "password": "bad"},
    )
    assert r.status_code == 401


def test_console_users_crud(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    headers = {"X-Admin-Key": "test-admin-key"}
    r = gateway_admin_client.get("/api/v1/admin/console-users", headers=headers)
    assert r.status_code == 200
    users = r.json().get("users") or []
    assert any(u["email"] == "admin@test.local" for u in users)

    r2 = gateway_admin_client.post(
        "/api/v1/admin/console-users",
        headers=headers,
        json={
            "email": "viewer@test.local",
            "nombre": "Viewer",
            "rol": "viewer",
            "password": "viewpass",
            "initials": "VW",
        },
    )
    assert r2.status_code == 200

    r3 = gateway_admin_client.patch(
        "/api/v1/admin/console-users?email=viewer@test.local",
        headers=headers,
        json={"nombre": "Viewer Updated"},
    )
    assert r3.status_code == 200
    assert r3.json()["user"]["nombre"] == "Viewer Updated"

    r4 = gateway_admin_client.delete(
        "/api/v1/admin/console-users?email=viewer@test.local",
        headers=headers,
    )
    assert r4.status_code == 200


def test_shared_grants(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    headers = {"X-Admin-Key": "test-admin-key"}
    r = gateway_admin_client.post(
        "/api/v1/admin/access/shared-grants",
        headers=headers,
        json={"tenant_id": "default", "user_id": "12345", "resource_key": "default"},
    )
    assert r.status_code == 200

    r2 = gateway_admin_client.get(
        "/api/v1/admin/access/shared-grants?tenant_id=default",
        headers=headers,
    )
    assert r2.status_code == 200
    grants = r2.json().get("grants") or []
    assert any(g["user_id"] == "12345" and g["resource_key"] == "default" for g in grants)

    r3 = gateway_admin_client.delete(
        "/api/v1/admin/access/shared-grants?tenant_id=default&user_id=12345&resource_key=default",
        headers=headers,
    )
    assert r3.status_code == 200


def test_access_overview(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    r = gateway_admin_client.get(
        "/api/v1/admin/access/overview?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["console_users"] >= 1
