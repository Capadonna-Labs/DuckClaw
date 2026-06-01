"""Tests llm_usage_log (costo estimado y agregados overview)."""
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

        con.execute(
            """
            CREATE TABLE llm_usage_log (
                id VARCHAR PRIMARY KEY,
                tenant_id VARCHAR NOT NULL,
                session_id VARCHAR,
                worker_id VARCHAR,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd DOUBLE NOT NULL DEFAULT 0,
                model VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        usage_rows = [
            ("u1", "default", "sess-a", "finanz", 1000, 500, 1500, 0.001, now - timedelta(days=1)),
            ("u2", "default", "sess-a", "finanz", 2000, 800, 2800, 0.002, now - timedelta(days=1)),
            ("u3", "default", "sess-b", "quant_trader", 5000, 2000, 7000, 0.005, now - timedelta(hours=5)),
            ("u4", "default", "sess-old", "finanz", 9000, 1000, 10000, 0.01, now - timedelta(days=20)),
        ]
        for uid, tenant_id, session_id, worker_id, inp, out, total, cost, created in usage_rows:
            con.execute(
                """
                INSERT INTO llm_usage_log
                  (id, tenant_id, session_id, worker_id, input_tokens, output_tokens, total_tokens, cost_usd, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [uid, tenant_id, session_id, worker_id, inp, out, total, cost, created],
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
    assert "usage" in data
    assert "db_path" in data

    by_worker = {a["worker_id"]: a for a in data["activity"]}
    assert by_worker["finanz"]["success_count"] == 1
    assert by_worker["finanz"]["failed_count"] == 1
    assert by_worker["quant_trader"]["success_count"] == 1
    assert by_worker["quant_trader"]["failed_count"] == 0

    assert len(data["latency"]) >= 1
    assert all("hour" in row and "avg_latency" in row for row in data["latency"])

    usage = data["usage"]
    assert usage["summary"]["total_tokens"] == 11300
    by_agent = {s["label"]: s for s in usage["series"]}
    assert by_agent["finanz"]["total_tokens"] == 4300
    assert by_agent["quant_trader"]["total_tokens"] == 7000


def test_overview_metrics_usage_group_by_session(gateway_admin_client: TestClient) -> None:
    r = gateway_admin_client.get(
        "/api/v1/admin/overview/metrics",
        params={"usage_group_by": "session", "worker_id": "finanz"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    usage = r.json()["usage"]
    labels = {s["label"] for s in usage["series"]}
    assert labels == {"sess-a"}
    assert usage["summary"]["total_tokens"] == 4300


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


def test_estimate_llm_cost_usd(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.llm_usage_log import estimate_llm_cost_usd, normalize_usage_tokens

    monkeypatch.setenv("DUCKCLAW_LLM_COST_INPUT_USD_PER_M", "1.0")
    monkeypatch.setenv("DUCKCLAW_LLM_COST_OUTPUT_USD_PER_M", "2.0")
    assert estimate_llm_cost_usd(1_000_000, 500_000) == pytest.approx(2.0)
    inp, out, total = normalize_usage_tokens(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    )
    assert (inp, out, total) == (100, 50, 150)
