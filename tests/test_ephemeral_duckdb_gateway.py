"""Regresión: gateway sin handle DuckDB persistente al archivo (concurrencia con db-writer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path


def test_gateway_db_ephemeral_readonly_opens_per_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import duckdb

    path = str(tmp_path / "ephemeral_gate.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    _c = duckdb.connect(path, read_only=False)
    _c.execute("SELECT 1")
    _c.close()
    monkeypatch.setenv("DUCKCLAW_DB_PATH", path)
    db = GatewayDbEphemeralReadonly(path)
    assert getattr(db, "_read_only", False) is True
    assert Path(get_gateway_db_path()).resolve() == Path(path).resolve()
    raw = db.query("SELECT 1 AS n")
    assert "1" in raw


def test_get_gateway_db_returns_ephemeral_facade(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = str(tmp_path / "gw_facade.duckdb")
    monkeypatch.setenv("DUCKCLAW_DB_PATH", path)
    from duckclaw.gateway_db import get_gateway_db

    g = get_gateway_db()
    assert isinstance(g, GatewayDbEphemeralReadonly)


def test_graph_server_get_db_is_ephemeral(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = str(tmp_path / "gs_get_db.duckdb")
    monkeypatch.setenv("DUCKCLAW_DB_PATH", path)
    from duckclaw.graphs import graph_server as gs

    monkeypatch.setattr(gs, "_graph_init_error", None)
    db = gs.get_db()
    assert isinstance(db, GatewayDbEphemeralReadonly)


def test_clear_worker_graph_cache_idempotent() -> None:
    from duckclaw.graphs.manager_graph import clear_worker_graph_cache

    clear_worker_graph_cache()
    clear_worker_graph_cache()
