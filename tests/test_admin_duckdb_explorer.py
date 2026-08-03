"""Tests admin DuckDB explorer (tabular, PGQ, vector). Spec: admin DuckDB explorer."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


def test_duckdb_actor_scope_falls_back_to_actor_tenant_not_gateway_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from duckclaw.admin_user_profiles import tenant_id_for_email

    gw_dir = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import core.admin_identity as admin_identity
    import routers.admin_domains.duckdb_explorer as duckdb_explorer

    def _raise_open_gateway_db(*_args, **_kwargs):
        raise RuntimeError("gateway db unavailable")

    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "test-tenant")
    monkeypatch.setattr(admin_identity, "open_gateway_db", _raise_open_gateway_db)

    scope = duckdb_explorer._duckdb_actor_scope("owner@example.com", "owner123")

    assert scope["actor_email"] == "owner@example.com"
    assert scope["vault_user_id"] == "owner123"
    assert scope["tenant_id"] == tenant_id_for_email("owner@example.com")
    assert scope["tenant_id"] != "test-tenant"


@pytest.fixture
def explorer_db(tmp_path: Path) -> Path:
    dbf = tmp_path / "explorer.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute("CREATE SCHEMA sample_schema")
    con.execute("CREATE TABLE sample_schema.rows (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO sample_schema.rows VALUES (1, 'alpha')")
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
               ('r2', 'newer chunk about trends', 'seed', 'PENDING')
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
    assert "sample_schema" in data.get("schemas", {})
    assert "rows" in data["schemas"]["sample_schema"]


def test_duckdb_tables_default_to_authenticated_actor_vault(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.admin_user_profiles import tenant_id_for_email

    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA actor_schema")
    con.execute("CREATE TABLE actor_schema.visible_table (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "test-tenant")

    response = gateway_admin_client.get(
        "/api/v1/admin/duckdb/tables",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vault_user_id"] == "owner123"
    assert data["actor_email"] == "owner@example.com"
    assert data["tenant_id"] == tenant_id_for_email("owner@example.com")
    assert data["tenant_id"] != "test-tenant"
    assert data["vault_path"].endswith("db/private/owner123/duckclaw.duckdb")
    assert data["schemas"]["actor_schema"] == ["visible_table"]


def test_duckdb_tables_show_extra_schemas_until_explicit_cleanup(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA actor_schema")
    con.execute("CREATE TABLE actor_schema.visible_table (id INTEGER)")
    for schema in ("archive_schema", "ops_schema"):
        con.execute(f"CREATE SCHEMA {schema}")
        con.execute(f"CREATE TABLE {schema}.legacy_table (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")

    response = gateway_admin_client.get(
        "/api/v1/admin/duckdb/tables",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
    )

    assert response.status_code == 200
    schemas = response.json()["schemas"]
    assert schemas["actor_schema"] == ["visible_table"]
    assert schemas["archive_schema"] == ["legacy_table"]
    assert schemas["ops_schema"] == ["legacy_table"]


def test_duckdb_legacy_schema_cleanup_requires_confirmation_and_drops_schema(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA cleanup_schema")
    con.execute("CREATE TABLE cleanup_schema.legacy_table (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")
    monkeypatch.setenv("DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS", "cleanup_schema")
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)

    listed = gateway_admin_client.get(
        "/api/v1/admin/duckdb/legacy-schemas",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
    )
    assert listed.status_code == 200
    assert "cleanup_schema" in [item["schema"] for item in listed.json()["schemas"]]

    rejected = gateway_admin_client.post(
        "/api/v1/admin/duckdb/legacy-schemas/drop",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
        json={"schemas": ["cleanup_schema"], "confirm": "wrong"},
    )
    assert rejected.status_code == 400

    response = gateway_admin_client.post(
        "/api/v1/admin/duckdb/legacy-schemas/drop",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"},
        json={"schemas": ["cleanup_schema"], "confirm": "DROP_LEGACY_SCHEMAS"},
    )

    assert response.status_code == 200
    assert response.json()["dropped"] == ["cleanup_schema"]
    con = duckdb.connect(str(user_db), read_only=True)
    try:
        remaining = {
            row[0]
            for row in con.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        }
    finally:
        con.close()
    assert "cleanup_schema" not in remaining


def test_duckdb_legacy_cleanup_detects_and_drops_configured_main_tables(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE TABLE main.archived_default_orders (id INTEGER)")
    con.execute("CREATE TABLE main.archived_default_products (id INTEGER)")
    con.execute("CREATE TABLE main.keep_me (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")
    monkeypatch.setenv(
        "DUCKCLAW_ADMIN_DUCKDB_LEGACY_MAIN_TABLES",
        "archived_default_orders,archived_default_products",
    )
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"}

    listed = gateway_admin_client.get(
        "/api/v1/admin/duckdb/legacy-schemas",
        headers=headers,
    )
    assert listed.status_code == 200
    assert {item["table"] for item in listed.json()["main_tables"]} == {
        "archived_default_orders",
        "archived_default_products",
    }

    rejected = gateway_admin_client.post(
        "/api/v1/admin/duckdb/legacy-schemas/drop",
        headers=headers,
        json={"main_tables": ["archived_default_orders"], "confirm": "wrong"},
    )
    assert rejected.status_code == 400

    dropped = gateway_admin_client.post(
        "/api/v1/admin/duckdb/legacy-schemas/drop",
        headers=headers,
        json={
            "main_tables": ["archived_default_orders", "archived_default_products"],
            "confirm": "DROP_LEGACY_SCHEMAS",
        },
    )
    assert dropped.status_code == 200
    assert dropped.json()["dropped_main_tables"] == [
        "archived_default_orders",
        "archived_default_products",
    ]

    con = duckdb.connect(str(user_db), read_only=True)
    try:
        remaining = {
            str(row[0])
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        con.close()
    assert "keep_me" in remaining
    assert "archived_default_orders" not in remaining
    assert "archived_default_products" not in remaining


def test_duckdb_legacy_schemas_can_be_configured_db_first(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    def fake_enqueue(command: object, *, db_path: str, user_id: str) -> str:
        _ = user_id
        gateway_con = duckdb.connect(db_path, read_only=False)
        try:
            dispatch_command(gateway_con, command.model_dump())
        finally:
            gateway_con.close()
        return command.task_id

    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA custom_legacy")
    con.execute("CREATE TABLE custom_legacy.legacy_table (id INTEGER)")
    con.close()
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")
    monkeypatch.delenv("DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS", raising=False)
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", fake_enqueue)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"}

    configured = gateway_admin_client.patch(
        "/api/v1/admin/settings/runtime",
        headers=headers,
        json={
            "settings": [
                {
                    "domain": "duckdb",
                    "key": "legacy_schemas",
                    "value": "custom_legacy",
                    "scope": "actor",
                }
            ]
        },
    )
    assert configured.status_code == 200

    listed = gateway_admin_client.get(
        "/api/v1/admin/duckdb/legacy-schemas",
        headers=headers,
    )

    assert listed.status_code == 200
    assert "custom_legacy" in [item["schema"] for item in listed.json()["schemas"]]


def test_duckdb_query_select(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={
            "vault_path": str(explorer_db),
            "query": "SELECT * FROM sample_schema.rows",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["columns"] == ["id", "name"]
    assert data["rows"] == [[1, "alpha"]]


def test_duckdb_query_insert(
    gateway_admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    user_dir = repo_root / "db" / "private" / "owner123"
    user_dir.mkdir(parents=True)
    user_db = user_dir / "duckclaw.duckdb"
    con = duckdb.connect(str(user_db))
    con.execute("CREATE SCHEMA sample_schema")
    con.execute("CREATE TABLE sample_schema.rows (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO sample_schema.rows VALUES (1, 'alpha')")
    con.close()
    monkeypatch.delenv("DUCKCLAW_EXTENSION_ROOT", raising=False)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "owner123")
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    monkeypatch.setattr("duckclaw.spawn_profile.spawn_inline_writes_enabled", lambda: True)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "owner@example.com"}

    r = gateway_admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=headers,
        json={
            "vault_path": "db/private/owner123/duckclaw.duckdb",
            "query": "INSERT INTO sample_schema.rows VALUES (2, 'beta')",
        },
    )
    if r.status_code != 200:
        raise AssertionError(f"{r.status_code} {r.json()}")
    data = r.json()
    assert data.get("mode") == "write"
    assert data.get("status") == "success"
    verify = gateway_admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=headers,
        json={
            "vault_path": "db/private/owner123/duckclaw.duckdb",
            "query": "SELECT id, name FROM sample_schema.rows ORDER BY id",
        },
    )
    assert verify.status_code == 200
    assert [2, "beta"] in verify.json()["rows"]


def test_duckdb_query_rejects_drop(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(explorer_db), "query": "DROP TABLE sample_schema.rows"},
    )
    assert r.status_code == 400


def test_duckdb_query_enforces_limit(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={
            "vault_path": str(explorer_db),
            "query": "SELECT * FROM sample_schema.rows",
        },
    )
    assert r.status_code == 200
    assert r.json().get("limit_applied") == 500


def test_duckdb_query_pagination_offset(admin_client: TestClient, tmp_path: Path) -> None:
    dbf = tmp_path / "page.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute("CREATE SCHEMA sample_schema")
    con.execute("CREATE TABLE sample_schema.rows (id INTEGER, name VARCHAR)")
    con.executemany(
        "INSERT INTO sample_schema.rows VALUES (?, ?)",
        [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e")],
    )
    con.close()

    r = admin_client.post(
        "/api/v1/admin/duckdb/query",
        headers=_ADMIN_HEADERS,
        json={
            "vault_path": str(dbf),
            "query": "SELECT id, name FROM sample_schema.rows ORDER BY id",
            "limit": 2,
            "offset": 2,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["rows"] == [[3, "c"], [4, "d"]]
    assert data["limit_applied"] == 2
    assert data["offset"] == 2
    assert data["has_more"] is True


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


def test_duckdb_pgq_bootstrap(
    admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUCKCLAW_ADMIN_EMAIL", "")
    empty = tmp_path / "pgq-empty.duckdb"
    duckdb.connect(str(empty)).close()

    before = admin_client.get(
        f"/api/v1/admin/duckdb/pgq-graph?vault_path={empty}",
        headers=_ADMIN_HEADERS,
    )
    assert before.status_code == 200
    assert before.json().get("warning")

    boot = admin_client.post(
        "/api/v1/admin/duckdb/pgq/bootstrap",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(empty)},
    )
    assert boot.status_code == 200
    payload = boot.json()
    assert payload["ok"] is True
    assert "memory_nodes" in payload["tables_created"]
    assert "memory_edges" in payload["tables_created"]
    assert isinstance(payload["pgq_available"], bool)

    after = admin_client.get(
        f"/api/v1/admin/duckdb/pgq-graph?vault_path={empty}",
        headers=_ADMIN_HEADERS,
    )
    assert after.status_code == 200
    assert not after.json().get("warning")


def test_duckdb_pgq_graph_html_missing(admin_client: TestClient, explorer_db: Path) -> None:
    r = admin_client.get(
        f"/api/v1/admin/duckdb/pgq-graph/html?vault_path={explorer_db}",
        headers=_ADMIN_HEADERS,
    )
    assert r.status_code == 404
    assert "no generado" in r.text.lower()


def test_duckdb_pgq_rebuild(
    admin_client: TestClient,
    explorer_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from core.pgq_graph_cache import memory_graph_html_path

    html_path = memory_graph_html_path(str(explorer_db))

    def _fake_run(cmd, **kwargs):
        out = kwargs.get("out") or html_path
        for i, part in enumerate(cmd):
            if part == "--out" and i + 1 < len(cmd):
                out = Path(cmd[i + 1])
                break
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<html><body>pgq graph</body></html>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    rebuild = admin_client.post(
        "/api/v1/admin/duckdb/pgq/rebuild",
        headers=_ADMIN_HEADERS,
        json={"vault_path": str(explorer_db)},
    )
    assert rebuild.status_code == 200
    data = rebuild.json()
    assert data["ok"] is True
    assert html_path.is_file()

    html = admin_client.get(
        f"/api/v1/admin/duckdb/pgq-graph/html?vault_path={explorer_db}",
        headers=_ADMIN_HEADERS,
    )
    assert html.status_code == 200
    assert "pgq graph" in html.text


def test_generate_memory_graph_self_check() -> None:
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "generate_memory_graph.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--self-check"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


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
        json={"vault_path": str(explorer_db), "query": "vector search trends", "limit": 5},
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
