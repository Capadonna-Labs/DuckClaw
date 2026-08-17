"""Regresión: liberar handle RW del worker antes de db-writer / RO del manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from duckclaw import DuckClaw


def test_release_file_handle_for_external_writer_closes_rw_python(tmp_path: Path) -> None:
    path = str(tmp_path / "vault.duckdb")
    duckdb.connect(path).close()
    db = DuckClaw(path, read_only=False, engine="python")
    assert db._con is not None
    db.release_file_handle_for_external_writer()
    assert db._con is None
    con2 = duckdb.connect(path, read_only=True)
    try:
        assert con2.execute("SELECT 1").fetchone() == (1,)
    finally:
        con2.close()


def test_query_uses_ephemeral_read_while_writer_defer_active(tmp_path: Path) -> None:
    path = str(tmp_path / "vault.duckdb")
    con = duckdb.connect(path)
    try:
        con.execute("CREATE TABLE t1(x INTEGER)")
        con.execute("INSERT INTO t1 VALUES (42)")
    finally:
        con.close()
    db = DuckClaw(path, read_only=True, engine="python")
    db.release_file_handle_for_external_writer()
    assert db._con is None
    assert db._external_writer_defer_active()
    out = db.query("SELECT x FROM t1")
    assert "42" in out
    assert db._con is None
    db.resume_file_handle()
    assert db._con is not None


def test_release_worker_db_handle_retains_graph_when_cache_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED", "true")
    from duckclaw.manager import manager_worker_cache as mwc

    mwc.clear_worker_graph_cache()
    path = str(tmp_path / "platform-orchestrator.duckdb")
    duckdb.connect(path).close()
    wdb = DuckClaw(path, read_only=False, engine="python")

    class _Graph:
        _worker_db = wdb

    graph = _Graph()
    key = "t::platform-orchestrator::" + path
    mwc.remember_worker_graph_cache(key, graph)
    assert mwc._release_worker_db_handle(graph, cache_key=key) is True
    assert wdb._con is None
    assert graph._worker_db is wdb
    assert mwc.worker_graph_cache_entry_count() == 1


def test_release_worker_db_handle_closes_and_pops_cache_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED", "false")
    from duckclaw.manager import manager_worker_cache as mwc

    mwc.clear_worker_graph_cache()
    path = str(tmp_path / "platform-orchestrator.duckdb")
    duckdb.connect(path).close()
    wdb = DuckClaw(path, read_only=False, engine="python")

    class _Graph:
        _worker_db = wdb

    graph = _Graph()
    key = "t::platform-orchestrator::" + path
    mwc._worker_graph_cache[key] = graph
    assert mwc.worker_graph_cache_entry_count() == 1
    assert mwc._release_worker_db_handle(graph, cache_key=key) is True
    assert wdb._con is None
    assert mwc.worker_graph_cache_entry_count() == 0
