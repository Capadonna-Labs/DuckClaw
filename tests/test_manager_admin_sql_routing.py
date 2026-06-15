"""Manager debe preparar mutaciones admin_sql sin asignar verticales hardcodeadas."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


def _seed_prompt_policy(con, policy_type: str, policy_name: str, content: str) -> None:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    con.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, active)
        VALUES (?, ?, ?, 1, 'active', ?, ?, true)
        """,
        [
            f"{policy_type}_{policy_name}_1",
            policy_type,
            policy_name,
            content,
            checksum,
        ],
    )


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


def test_plan_task_does_not_override_worker_for_admin_sql():
    mg = _load_manager_graph()
    planned, override = mg._plan_task("Crea la tabla con admin_sql", "custom-worker")
    assert override is None
    assert "admin_sql" in planned.lower() or "TAREA" in planned


def test_plan_task_uses_db_prompt_policy_for_db_tool_pressure():
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_prompt_policy(
        con,
        "manager_task",
        "db_tool_pressure",
        "DB policy: usa admin_sql para mutaciones DuckDB.",
    )

    mg = _load_manager_graph()
    planned, override = mg._plan_task(
        "Crea la tabla con admin_sql",
        "custom-worker",
        prompt_policies=PromptPolicyResolver(con),
    )

    assert override is None
    assert "DB policy: usa admin_sql" in planned
    assert "--- Mensaje del usuario ---" in planned
    assert "Crea la tabla con admin_sql" in planned
