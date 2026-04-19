"""Tests para helpers de scripts/verify_pqrsd_telegram_pipeline.py (sin red)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_pqrsd_telegram_pipeline",
    _REPO / "scripts" / "verify_pqrsd_telegram_pipeline.py",
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
vault_user_id_from_db_path = _mod.vault_user_id_from_db_path


def test_vault_user_id_from_private_path() -> None:
    p = Path("/repo/db/private/1726618406/pqrsd-assistantdb1.duckdb")
    assert vault_user_id_from_db_path(p) == "1726618406"


def test_vault_user_id_requires_private_segment() -> None:
    p = Path("/repo/db/duckclaw.duckdb")
    with pytest.raises(SystemExit):
        vault_user_id_from_db_path(p)
