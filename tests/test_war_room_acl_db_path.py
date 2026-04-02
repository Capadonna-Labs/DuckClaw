"""DUCKCLAW_WAR_ROOM_ACL_DB_PATH: misma semántica que spec en plan WR Telegram."""

from __future__ import annotations

import pytest

from duckclaw.gateway_db import get_gateway_db_path, get_war_room_acl_db_path


def test_get_war_room_acl_db_path_defaults_to_gateway_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", raising=False)
    monkeypatch.setenv("DUCKCLAW_DB_PATH", "/tmp/gw.duckdb")
    assert get_war_room_acl_db_path() == "/tmp/gw.duckdb"
    assert get_war_room_acl_db_path() == get_gateway_db_path()


def test_get_war_room_acl_db_path_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_DB_PATH", "/tmp/gw.duckdb")
    monkeypatch.setenv("DUCKCLAW_WAR_ROOM_ACL_DB_PATH", "/tmp/finanz_wr.duckdb")
    assert get_war_room_acl_db_path() == "/tmp/finanz_wr.duckdb"
    assert get_gateway_db_path() == "/tmp/gw.duckdb"
