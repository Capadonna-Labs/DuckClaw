"""Manager debe delegar mutaciones admin_sql a finanz (RW), no a quant-trader (RO)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_manager_graph():
    root = Path(__file__).resolve().parents[1]
    mod_path = root / "packages/agents/src/duckclaw/graphs/manager_graph.py"
    spec = importlib.util.spec_from_file_location("manager_graph_test", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_duckdb_admin_write_intent_detects_admin_sql():
    mg = _load_manager_graph()
    assert mg._duckdb_admin_write_intent("Crea la tabla con admin_sql")
    assert mg._duckdb_admin_write_intent("Ejecuta CREATE TABLE foo (id INT)")
    assert not mg._duckdb_admin_write_intent("¿cuál es mi saldo?")


def test_plan_task_overrides_to_finanz_for_admin_sql():
    mg = _load_manager_graph()
    planned, override = mg._plan_task("Crea la tabla con admin_sql", "quant-trader")
    assert override == "finanz"
    assert "admin_sql" in planned.lower() or "TAREA" in planned
