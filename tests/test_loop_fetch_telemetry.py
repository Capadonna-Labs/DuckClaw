"""Telemetry sweep against in-memory DuckDB."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from harness_core.skills.fetch_system_telemetry import fetch_system_telemetry
from harness_core.states.loop_state import HomeostasisTarget


def _seed_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE task_audit_log (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE SCHEMA IF NOT EXISTS main;
        CREATE TABLE main.semantic_memory (
            id VARCHAR PRIMARY KEY,
            content TEXT,
            embedding_status VARCHAR DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO task_audit_log VALUES ('t1','default','w','q','SUCCESS',100,now(),'')"
    )
    con.execute(
        "INSERT INTO task_audit_log VALUES ('t2','default','w','q','FAILED',200,now(),'')"
    )
    con.execute(
        """
        INSERT INTO task_audit_log
        VALUES ('stale-1','default','w','q','PENDING',0,CURRENT_TIMESTAMP - INTERVAL '25 hours','')
        """
    )
    con.execute("INSERT INTO main.semantic_memory VALUES ('m1','a','PENDING',now(),now())")
    con.execute("INSERT INTO main.semantic_memory VALUES ('m2','b','OK',now(),now())")
    con.close()


def test_fetch_system_telemetry_audit_and_memory(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.duckdb"
    _seed_db(db_path)
    metrics, stale_ids, mem_ids, locks = fetch_system_telemetry(
        str(db_path),
        tenant_id="default",
        delta_interval_seconds=3600,
        targets=HomeostasisTarget(),
    )
    assert metrics.error_rate_pct == 50.0
    assert metrics.avg_latency_ms == 150.0
    assert metrics.stale_tasks_count == 1
    assert stale_ids == ["stale-1"]
    assert 0.0 <= metrics.memory_fragmentation_index <= 1.0
    assert locks == 0
    assert isinstance(stale_ids, list)
    assert isinstance(mem_ids, list)
