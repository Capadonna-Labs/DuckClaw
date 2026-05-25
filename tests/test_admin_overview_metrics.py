"""Tests GET /api/v1/admin/overview/metrics (task_audit_log aggregates)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gateway_admin_client(gateway_db: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from gateway_import import load_gateway_app

    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    return TestClient(load_gateway_app())


@pytest.fixture
def gateway_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS

    p = tmp_path / "gateway_metrics.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(p))
    now = datetime.now(timezone.utc)
    con = duckdb.connect(str(p))
    try:
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
            );
            """
        )
        rows = [
            ("t1", "default", "finanz", "q1", "SUCCESS", 100, now - timedelta(hours=2)),
            ("t2", "default", "finanz", "q2", "FAILED", 200, now - timedelta(hours=3)),
            ("t3", "default", "quant_trader", "q3", "SUCCESS", 5000, now - timedelta(hours=1)),
            ("t4", "default", "finanz", "q4", "SUCCESS", 3000, now - timedelta(days=10)),
        ]
        for task_id, tenant_id, worker_id, qp, status, dur, created in rows:
            con.execute(
                """
                INSERT INTO task_audit_log
                  (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [task_id, tenant_id, worker_id, qp, status, dur, created],
            )
    finally:
        con.close()
    return p


def test_overview_metrics_ok(gateway_admin_client: TestClient) -> None:
    r = gateway_admin_client.get(
        "/api/v1/admin/overview/metrics",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "activity" in data
    assert "latency" in data
    assert "db_path" in data

    by_worker = {a["worker_id"]: a for a in data["activity"]}
    assert by_worker["finanz"]["success_count"] == 1
    assert by_worker["finanz"]["failed_count"] == 1
    assert by_worker["quant_trader"]["success_count"] == 1
    assert by_worker["quant_trader"]["failed_count"] == 0

    assert len(data["latency"]) >= 1
    assert all("hour" in row and "avg_latency" in row for row in data["latency"])


def test_overview_metrics_missing_hub(
    gateway_admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: "/nonexistent/duckclaw_metrics_missing.duckdb",
    )
    r = gateway_admin_client.get(
        "/api/v1/admin/overview/metrics",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 503
