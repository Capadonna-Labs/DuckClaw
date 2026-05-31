"""Tests Admin Access API (console users, login, shared grants)."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from duckclaw.admin_auth_crypto import calculate_login_delay, verify_and_migrate
from duckclaw.admin_console_users import (
    authenticate_console_user,
    ensure_admin_auth_columns,
    ensure_admin_console_users_table,
    get_by_email,
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


def _pbkdf2_hash(plain: str, *, iterations: int = 260_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
    )


def test_argon2_password_authenticates(gateway_db: Path) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        upsert_console_user(
            adapter,
            email="argon@test.local",
            nombre="Argon",
            rol="admin",
            password="hunter2!!",
            initials="AR",
        )
        ok = authenticate_console_user(adapter, email="argon@test.local", password="hunter2!!")
        assert ok is not None
        row = get_by_email(adapter, "argon@test.local")
        assert row is not None
        assert str(row.get("hash_algo") or "") == "argon2id"
    finally:
        con.close()


def test_pbkdf2_verify_password_legacy() -> None:
    stored = _pbkdf2_hash("hunter2")
    assert verify_password("hunter2", stored)
    assert not verify_password("wrongpass", stored)


def test_verify_and_migrate_pbkdf2_to_argon2(gateway_db: Path) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        stored = _pbkdf2_hash("migrateme1")
        adapter.execute(
            """
            INSERT INTO main.admin_console_users
              (email, nombre, rol, password_hash, hash_algo, initials, active)
            VALUES ('migrate@test.local', 'Migrate', 'admin', ?, 'pbkdf2_sha256', 'MG', true)
            """,
            [stored],
        )
        row = get_by_email(adapter, "migrate@test.local")
        assert row is not None

        updates: list[tuple[str, str, dict]] = []

        def capture(email: str, pwd_hash: str, algo: str, params: dict) -> None:
            updates.append((algo, pwd_hash, params))
            adapter.execute(
                "UPDATE main.admin_console_users SET password_hash=?, hash_algo=?, hash_params=?::JSON WHERE email=?",
                [pwd_hash, algo, json.dumps(params), email],
            )

        assert verify_and_migrate("migrate@test.local", "migrateme1", row, capture)
        assert updates
        assert updates[0][0] == "argon2id"
    finally:
        con.close()


def test_calculate_login_delay_edges() -> None:
    assert calculate_login_delay(0) == 0
    assert calculate_login_delay(4) == 0
    assert calculate_login_delay(5) == 1
    assert calculate_login_delay(6) == 2
    assert calculate_login_delay(20) == 3600


def test_admin_auth_columns_idempotent(gateway_db: Path) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ensure_admin_auth_columns(adapter)
        ensure_admin_auth_columns(adapter)
    finally:
        con.close()


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


def test_admin_login_seeds_default_when_table_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_redis
) -> None:
    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS
    from gateway_import import load_gateway_app

    p = tmp_path / "empty_gateway.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(p))
    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_ADMIN_PASSWORD", "seedpass1")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(Path(__file__).resolve().parent.parent))
    con = duckdb.connect(str(p))
    try:
        ensure_admin_console_users_table(_Adapter(con))
    finally:
        con.close()

    client = TestClient(load_gateway_app())
    client.app.state.redis = session_redis
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@duckclaw.local", "password": "seedpass1"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "admin@duckclaw.local"


def test_admin_login_ok(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    r = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.local", "password": "secret123"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == "admin@test.local"
    assert data["user"]["rol"] == "admin"
    assert "session" in r.cookies


def test_admin_login_fail(gateway_admin_client: TestClient, gateway_db: Path) -> None:
    r = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.local", "password": "wrongpass1"},
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
    assert "db_path" in data
    assert "db_exists" in data
    assert data["persistence_tables"]["console"] == "main.admin_console_users"
    assert data["persistence_tables"]["telegram"] == "main.authorized_users"
    assert data["persistence_tables"]["shared"] == "main.user_shared_db_access"
