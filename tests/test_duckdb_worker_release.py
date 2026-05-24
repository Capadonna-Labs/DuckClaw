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


def test_release_worker_db_handle_closes_and_pops_cache(tmp_path: Path) -> None:
    from duckclaw.graphs import manager_graph as mg

    path = str(tmp_path / "finanz.duckdb")
    duckdb.connect(path).close()
    wdb = DuckClaw(path, read_only=False, engine="python")
    graph = MagicMock()
    graph._worker_db = wdb
    key = "t::finanz::" + path
    mg._worker_graph_cache[key] = graph
    assert mg.worker_graph_cache_entry_count() == 1
    assert mg._release_worker_db_handle(graph, cache_key=key) is True
    assert wdb._con is None
    assert mg.worker_graph_cache_entry_count() == 0
