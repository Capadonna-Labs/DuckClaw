"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from env_ids import owner_user_id_from_env, test_telegram_user_id_from_env

# Permite `from scripts.foo import ...` en tests (p. ej. sanitize_traces_for_gemma).
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# DuckDB INSTALL json: home escribible (evita ~/.duckdb en CI/sandbox).
_pytest_duckdb_home = _repo_root / ".pytest_duckdb"
_pytest_duckdb_home.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DUCKCLAW_TEST_DUCKDB_HOME", str(_pytest_duckdb_home))

# API Gateway y db-writer exigen REDIS_URL o DUCKCLAW_REDIS_URL (sin fallback en código).
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")


@pytest.fixture(autouse=True)
def _isolate_test_env_from_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    from env_isolation import isolate_test_env_from_dotenv

    isolate_test_env_from_dotenv(monkeypatch)


@pytest.fixture
def owner_user_id() -> str:
    """``DUCKCLAW_OWNER_ID`` / ``DUCKCLAW_ADMIN_CHAT_ID`` desde .env."""
    uid = owner_user_id_from_env()
    if not uid:
        pytest.skip("Definir DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID en .env")
    return uid


@pytest.fixture
def test_telegram_user_id() -> str:
    return test_telegram_user_id_from_env()


@pytest.fixture
def admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", "")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(_repo_root))
    return TestClient(load_gateway_app())


class SessionFakeRedis:
    """Minimal async Redis for admin session tests."""

    def __init__(self) -> None:
        import time

        self._time = time
        self._values: dict[str, str] = {}
        self._expiry: dict[str, float] = {}

    def _purge(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and exp <= self._time.monotonic():
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    async def incr(self, key: str) -> int:
        self._purge(key)
        n = int(self._values.get(key, "0")) + 1
        self._values[key] = str(n)
        return n

    async def expire(self, key: str, seconds: int) -> bool:
        self._expiry[key] = self._time.monotonic() + int(seconds)
        return True

    async def get(self, key: str) -> str | None:
        self._purge(key)
        return self._values.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._values[key] = value
        self._expiry[key] = self._time.monotonic() + int(seconds)
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._values or key in self._expiry:
                removed += 1
            self._values.pop(key, None)
            self._expiry.pop(key, None)
        return removed

    async def ttl(self, key: str) -> int:
        self._purge(key)
        exp = self._expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - self._time.monotonic()))


@pytest.fixture
def session_redis() -> SessionFakeRedis:
    return SessionFakeRedis()


class _GatewayDbAdapter:
    def __init__(self, con) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


@pytest.fixture
def gateway_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import duckdb

    from duckclaw.admin_console_users import ensure_admin_console_users_table, upsert_console_user
    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS
    from duckclaw.shared_db_grants import ensure_user_shared_db_access_table

    p = tmp_path / "gateway.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(p))
    con = duckdb.connect(str(p))
    try:
        adapter = _GatewayDbAdapter(con)
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


@pytest.fixture
def gateway_admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch, session_redis) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(_repo_root))
    client = TestClient(load_gateway_app())
    client.app.state.redis = session_redis
    return client
