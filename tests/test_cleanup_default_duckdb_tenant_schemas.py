from __future__ import annotations

from types import ModuleType

import duckdb


def _load_cleanup_module() -> ModuleType:
    import duckops.db_cleanup_tenant as cleanup

    return cleanup


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
