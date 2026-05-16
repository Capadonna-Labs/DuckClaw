"""Pytest: variables de entorno por defecto para tests (sin secretos)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

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

# Cargar .env del repo (sin sobreescribir vars ya exportadas en CI/shell).
_env_file = _repo_root / ".env"
if _env_file.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file, override=False)
    except ImportError:
        pass


def owner_user_id_from_env() -> str:
    """ID del owner/admin para tests de gateway (Telegram Guard bypass)."""
    return (
        (os.environ.get("DUCKCLAW_OWNER_ID") or "").strip()
        or (os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    )


@pytest.fixture
def owner_user_id() -> str:
    """``DUCKCLAW_OWNER_ID`` / ``DUCKCLAW_ADMIN_CHAT_ID`` desde .env (sin hardcode en tests)."""
    uid = owner_user_id_from_env()
    if not uid:
        pytest.skip("Definir DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID en .env")
    return uid
