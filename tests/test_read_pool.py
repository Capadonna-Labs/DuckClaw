"""Tests for ephemeral concurrent read pool (spec: Concurrent Tool Node)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy
from duckclaw.workers.manifest import WorkerSpec
from duckclaw.workers.read_pool import (
    build_attach_statements,
    should_parallelize_ephemeral_tool_calls,
    validate_worker_read_sql,
)


def _minimal_spec() -> WorkerSpec:
    return WorkerSpec(
        worker_id="t",
        logical_worker_id="t",
        name="t",
        schema_name="main",
        llm_required=None,
        temperature=0.0,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=True,
        worker_dir=Path("."),
    )


def _spec_with_runtime_capability(capability_name: str) -> WorkerSpec:
    spec = _minimal_spec()
    capability = WorkerCapability(
        capability_id=f"cap_{capability_name}",
        name=capability_name,
        kind="runtime_policy",
        provider="duckclaw",
        permission="use",
        config={},
        policy={},
        quota={},
    )
    spec.runtime_policy = WorkerRuntimePolicy(
        worker_id=spec.worker_id,
        identity=None,
        capabilities=(capability,),
    )
    return spec


def test_should_parallelize_rules() -> None:
    assert not should_parallelize_ephemeral_tool_calls([])
    assert not should_parallelize_ephemeral_tool_calls([{"name": "read_sql"}])
    assert should_parallelize_ephemeral_tool_calls(
        [{"name": "read_sql"}, {"name": "read_sql"}]
    )
    assert should_parallelize_ephemeral_tool_calls(
        [{"name": "read_sql"}, {"name": "inspect_schema"}]
    )
    assert not should_parallelize_ephemeral_tool_calls(
        [{"name": "read_sql"}, {"name": "run_sandbox"}]
    )


def test_build_attach_skips_duplicate_shared_file(tmp_path: Path) -> None:
    db = tmp_path / "w.duckdb"
    db.write_bytes(b"")
    p = str(db)
    stmts = build_attach_statements(p, p, p)
    assert len(stmts) == 1
    assert "AS private" in stmts[0]


def test_validate_read_sql_empty() -> None:
    err = validate_worker_read_sql(_minimal_spec(), "")
    assert err is not None
    assert "vacío" in err.lower() or "error" in err.lower()


def test_validate_read_sql_blocks_write() -> None:
    err = validate_worker_read_sql(_minimal_spec(), "DELETE FROM x")
    assert err is not None


def test_read_pool_has_no_bi_analyst_worker_special_case() -> None:
    source = Path("packages/agents/src/duckclaw/workers/read_pool.py").read_text(encoding="utf-8")

    assert "bi_analyst" not in source


def test_validate_read_sql_blocks_unbounded_select_star_via_runtime_capability() -> None:
    err = validate_worker_read_sql(
        _spec_with_runtime_capability("bounded_select_star_read"),
        "SELECT * FROM events",
    )

    assert err is not None
    assert "select *" in err.lower()


def test_validate_read_sql_allows_unbounded_select_star_without_runtime_capability() -> None:
    err = validate_worker_read_sql(_minimal_spec(), "SELECT * FROM events")

    assert err is None


@pytest.mark.skipif(
    not __import__("importlib.util").util.find_spec("duckdb"),
    reason="duckdb not installed",
)
def test_run_ephemeral_read_sql_smoke(tmp_path: Path) -> None:
    import duckdb

    from duckclaw.workers.read_pool import run_ephemeral_read_sql

    dbf = tmp_path / "x.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute("CREATE TABLE t (i INT); INSERT INTO t VALUES (1);")
    con.close()
    p = str(dbf)
    spec = _minimal_spec()
    out = run_ephemeral_read_sql(spec, p, p, None, [], "SELECT * FROM t")
    assert "1" in out
