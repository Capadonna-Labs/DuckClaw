"""Regresión: mutaciones whitelist usan motor Python al abrir hub aparte del fly_db."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from duckclaw.gateway_db import GatewayDbEphemeralReadonly
from duckclaw.graphs.on_the_fly_commands import _authorized_users_rw_connection


def _bootstrap_duckdb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=False)
    try:
        con.execute("SELECT 1")
    finally:
        con.close()


def test_authorized_users_rw_opens_hub_with_python_engine_when_vault_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    for k in (
        "DUCKCLAW_WAR_ROOM_ACL_DB_PATH",
        "DUCKCLAW_FINANZ_DB_PATH",
        "DUCKCLAW_JOB_HUNTER_DB_PATH",
        "DUCKCLAW_SIATA_DB_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    hub = tmp_path / "hub.duckdb"
    vault = tmp_path / "vault.duckdb"
    _bootstrap_duckdb(hub)
    _bootstrap_duckdb(vault)
    monkeypatch.setenv("DUCKDB_PATH", str(hub))

    def _fake_get_db() -> GatewayDbEphemeralReadonly:
        return GatewayDbEphemeralReadonly(str(hub.resolve()))

    monkeypatch.setattr(
        "duckclaw.graphs.graph_server.get_db",
        _fake_get_db,
    )

    from duckclaw import DuckClaw

    fly_db = DuckClaw(str(vault.resolve()), read_only=False, engine="python")

    with patch("duckclaw.DuckClaw", wraps=DuckClaw) as spy:
        mut_db, mut_close = _authorized_users_rw_connection(fly_db)
        try:
            spy.assert_called()
            _kwargs = spy.call_args[1]
            assert _kwargs.get("read_only") is False
            assert _kwargs.get("engine") == "python"
        finally:
            mut_close()
            fly_db.close()


def test_team_whitelist_audit_helpers_respect_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import on_the_fly_commands as m

    monkeypatch.delenv("DUCKCLAW_TEAM_WHITELIST_DEBUG", raising=False)
    assert m._team_whitelist_audit_enabled() is False
    monkeypatch.setenv("DUCKCLAW_TEAM_WHITELIST_DEBUG", "1")
    assert m._team_whitelist_audit_enabled() is True
