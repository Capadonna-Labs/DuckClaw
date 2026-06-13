"""Gateway DB path stays generic; War Room no longer has a dedicated ACL path env."""

from __future__ import annotations

from pathlib import Path

import pytest

import duckclaw.gateway_db as gateway_db


def test_gateway_db_path_ignores_removed_war_room_acl_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUCKCLAW_TENANT_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_VAULT_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "/tmp/gw.duckdb")

    assert Path(gateway_db.get_gateway_db_path()) == Path("/tmp/gw.duckdb").resolve()
    assert not any(key.endswith("_WAR_ROOM_ACL_DB_PATH") for key in gateway_db.GATEWAY_DB_ENV_KEYS)


def test_gateway_db_module_does_not_expose_war_room_acl_path_helper() -> None:
    removed_helper = "get_war_room_acl" "_db_path"
    assert not hasattr(gateway_db, removed_helper)
