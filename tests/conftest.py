"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

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
