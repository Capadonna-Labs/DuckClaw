"""DUCKCLAW_WAR_ROOM_ACL_DB_PATH: misma semántica que spec en plan WR Telegram."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.gateway_db import get_gateway_db_path, get_war_room_acl_db_path


def test_get_war_room_acl_db_path_defaults_to_gateway_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_JOB_HUNTER_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_SIATA_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", "/tmp/gw.duckdb")
    assert Path(get_war_room_acl_db_path()) == Path("/tmp/gw.duckdb").resolve()
    assert get_war_room_acl_db_path() == get_gateway_db_path()


def test_get_war_room_acl_db_path_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_JOB_HUNTER_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_SIATA_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_FINANZ_DB_PATH", "/tmp/gw.duckdb")
    monkeypatch.setenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", "/tmp/finanz_wr.duckdb")
    assert Path(get_war_room_acl_db_path()) == Path("/tmp/finanz_wr.duckdb").resolve()
    # WAR_ROOM_ACL va primero en GATEWAY_DB_ENV_KEYS: el hub efectivo es esa ruta.
    assert Path(get_gateway_db_path()) == Path("/tmp/finanz_wr.duckdb").resolve()
