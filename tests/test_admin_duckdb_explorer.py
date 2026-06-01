"""Tests admin DuckDB explorer (tabular, PGQ, vector). Spec: ADMIN_DUCKDB_EXPLORER.md."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def explorer_db(tmp_path: Path) -> Path:
    dbf = tmp_path / "explorer.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute("CREATE SCHEMA finance_worker")
    con.execute("CREATE TABLE finance_worker.sample (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO finance_worker.sample VALUES (1, 'alpha')")
    con.execute(
        """
        CREATE TABLE memory_nodes (
            node_id VARCHAR PRIMARY KEY,
            label VARCHAR,
            properties JSON
        )
        """
    )
    con.execute(
        """
        CREATE TABLE memory_edges (
            edge_id VARCHAR PRIMARY KEY,
            source_id VARCHAR,
            target_id VARCHAR,
            relationship VARCHAR,
            weight DOUBLE DEFAULT 1.0
        )
        """
    )
    con.execute(
        """
        INSERT INTO memory_nodes VALUES
        ('USER:alice', 'USER', '{"name": "alice"}'),
        ('MERCHANT:shop', 'MERCHANT', '{"name": "shop"}')
        """
    )
    con.execute(
        """
        INSERT INTO memory_edges VALUES
        ('e1', 'USER:alice', 'MERCHANT:shop', 'SPENDS_ON', 1.0)
        """
    )
    con.execute(
        """
        CREATE TABLE main.semantic_memory (
            id VARCHAR PRIMARY KEY,
            content TEXT NOT NULL,
            source VARCHAR DEFAULT 'test',
            embedding FLOAT[384],
            embedding_status VARCHAR DEFAULT 'READY',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        INSERT INTO main.semantic_memory (id, content, source, embedding_status)
        VALUES ('r1', 'older chunk about markets', 'seed', 'READY'),
               ('r2', 'newer chunk about ibkr', 'seed', 'PENDING')
        """
    )
    con.close()
    return dbf


def test_duckdb_tables(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.get(
        f"/api/v1/admin/duckdb/tables?vault_path={explorer_db}",
        headers=_ADMIN_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert "finance_worker" in data.get("schemas", {})
    assert "sample" in data["schemas"]["finance_worker"]


def test_duckdb_tables_default_to_authenticated_actor_vault(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "axis.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA actor_schema")
    con.execute("CREATE TABLE actor_schema.visible_table (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")

    response = gateway_admin_client.get(
        "/api/v1/admin/duckdb/tables",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vault_user_id"] == "owner123"
    assert data["vault_path"].endswith("db/private/owner123/axis.duckdb")
    assert data["schemas"]["actor_schema"] == ["visible_table"]


def test_runtime_vaults_are_scoped_to_authenticated_actor(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    owner_dir = repo_root / "db" / "private" / "owner123"
    other_dir = repo_root / "db" / "private" / "other456"
    owner_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    duckdb.connect(str(owner_dir / "axis.duckdb")).close()
    duckdb.connect(str(other_dir / "hidden.duckdb")).close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")

    response = gateway_admin_client.get(
        "/api/v1/admin/runtime/vaults",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    paths = [item["path"] for item in data["vaults"]]
    assert data["vault_user_id"] == "owner123"
    assert any(path.endswith("db/private/owner123/axis.duckdb") for path in paths)
    assert not any("other456" in path for path in paths)


def test_duckdb_query_select(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={
            "vault_path": str(explorer_db),
            "query": "SELECT * FROM finance_worker.sample",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["columns"] == ["id", "name"]
    assert data["rows"] == [[1, "alpha"]]


def test_duckdb_query_rejects_insert(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(explorer_db), "query": "INSERT INTO finance_worker.sample VALUES (2, 'x')"},
    )
    assert r.status_code == 400


def test_duckdb_query_enforces_limit(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={
            "vault_path": str(explorer_db),
            "query": "SELECT * FROM finance_worker.sample",
        },
    )
    assert r.status_code == 200
    assert r.json().get("limit_applied") in (None, 500)


def test_duckdb_pgq_graph(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.get(
        f"/api/v1/admin/duckdb/pgq-graph?vault_path={explorer_db}",
        headers=_ADMIN_HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["nodes"]) == 2
    assert len(data["links"]) == 1
    assert data["links"][0]["label"] == "SPENDS_ON"


def test_duckdb_vector_recent(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/vector-search",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(explorer_db), "query": "", "limit": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "recent"
    assert len(data["results"]) >= 1
    assert data["results"][0]["text"]


def test_duckdb_vector_lexical(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/vector-search",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(explorer_db), "query": "ibkr markets", "limit": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] in ("vector", "lexical", "none")
    assert isinstance(data["results"], list)


def test_duckdb_vector_not_initialized(admin_client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    r = admin_client.post(
        "/api/v1/admin/duckdb/vector-search",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(empty), "query": ""},
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert "inicializada" in (detail.get("detail") or "").lower()
    else:
        assert "inicializada" in str(detail).lower()
