from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
CLEANUP_SCRIPT = REPO_ROOT / "scripts" / "cleanup_default_duckdb_tenant_schemas.py"


def _load_cleanup_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cleanup_default_duckdb_tenant_schemas", CLEANUP_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_cleanup_only_drops_explicitly_configured_schemas() -> None:
    cleanup = _load_cleanup_module()
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("CREATE SCHEMA legacy_one")
        conn.execute("CREATE SCHEMA keep_one")

        drop_schemas, drop_tables = cleanup._plan_cleanup(
            conn,
            drop_schema_names={"legacy_one"},
            drop_main_table_names=(),
        )
    finally:
        conn.close()

    assert drop_schemas == ["legacy_one"]
    assert drop_tables == []
