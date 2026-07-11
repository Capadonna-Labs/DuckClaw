"""Tests for default MCP connector bootstrap and manifest-gated grants."""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import pytest

from duckclaw.admin_mcp_connectors import list_worker_mcp_connectors
from duckclaw.mcp_connector_defaults import (
    backfill_default_mcp_connectors_and_grants,
    ensure_default_mcp_connectors,
    manifest_has_skill,
    sync_worker_mcp_grants_from_manifest,
)
from duckclaw.mcp_connector_presets import default_mcp_connector_preset_ids
from duckclaw.schema_migrations import run_pending_migrations


@pytest.fixture
def mcp_db():
    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "mcp_defaults.duckdb"))
    run_pending_migrations(con)
    yield con
    con.close()


def test_default_preset_ids_include_remote_http_oauth() -> None:
    assert "remote_http_oauth" in default_mcp_connector_preset_ids()


def test_manifest_has_skill_parses_string_and_dict() -> None:
    assert manifest_has_skill({"skills": ["higgsfield", "research"]}, "higgsfield")
    assert manifest_has_skill({"skills": [{"higgsfield": {"enabled": True}}]}, "higgsfield")
    assert not manifest_has_skill({"skills": ["research"]}, "higgsfield")


def test_ensure_default_mcp_connectors_creates_remote_http_oauth(mcp_db) -> None:
    result = ensure_default_mcp_connectors(mcp_db, tenant_id="default", actor_email="admin@test.local")
    assert "mcp_remote_http_oauth" in result["created"] or result["created"] == []
    row = mcp_db.execute(
        "SELECT connector_id, preset_id, transport FROM main.admin_mcp_connectors "
        "WHERE connector_id = 'mcp_remote_http_oauth'"
    ).fetchone()
    assert row is not None
    assert row[1] == "remote_http_oauth"
    assert row[2] == "streamable_http"


def test_sync_grants_when_manifest_skill_matches_connector(mcp_db) -> None:
    ensure_default_mcp_connectors(mcp_db, tenant_id="default", actor_email="admin@test.local")
    worker_uid = "wrk_test_hf"
    mcp_db.execute(
        "INSERT INTO main.admin_worker_catalog "
        "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active) "
        "VALUES (?, 'default', 'admin@test.local', 'test-hf', 'Test HF', 'runtime', true)",
        [worker_uid],
    )
    manifest = {"skills": ["higgsfield"]}
    result = sync_worker_mcp_grants_from_manifest(
        mcp_db,
        worker_uid=worker_uid,
        tenant_id="default",
        manifest=manifest,
        actor_email="admin@test.local",
    )
    assert "mcp_remote_http_oauth" in result["granted"]
    connectors = list_worker_mcp_connectors(mcp_db, worker_uid=worker_uid, tenant_id="default")
    assert any(c["connector_id"] == "mcp_remote_http_oauth" for c in connectors)


def test_sync_revokes_when_manifest_skill_removed(mcp_db) -> None:
    ensure_default_mcp_connectors(mcp_db, tenant_id="default", actor_email="admin@test.local")
    worker_uid = "wrk_test_revoke"
    mcp_db.execute(
        "INSERT INTO main.admin_worker_catalog "
        "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active) "
        "VALUES (?, 'default', 'admin@test.local', 'test-revoke', 'Test Revoke', 'runtime', true)",
        [worker_uid],
    )
    sync_worker_mcp_grants_from_manifest(
        mcp_db,
        worker_uid=worker_uid,
        tenant_id="default",
        manifest={"skills": ["higgsfield"]},
    )
    sync_worker_mcp_grants_from_manifest(
        mcp_db,
        worker_uid=worker_uid,
        tenant_id="default",
        manifest={"skills": ["research"]},
    )
    row = mcp_db.execute(
        "SELECT active FROM main.admin_worker_mcp_grants "
        "WHERE worker_uid = ? AND connector_id = 'mcp_remote_http_oauth'",
        [worker_uid],
    ).fetchone()
    assert row is not None
    assert row[0] is False


def test_backfill_default_mcp_connectors_idempotent_with_multiple_tenants(mcp_db) -> None:
    mcp_db.execute(
        "INSERT INTO main.admin_worker_catalog "
        "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active) "
        "VALUES ('wrk_a', 'tenant_a', 'a@test.local', 'worker-a', 'A', 'runtime', true)"
    )
    mcp_db.execute(
        "INSERT INTO main.admin_worker_catalog "
        "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active) "
        "VALUES ('wrk_b', 'tenant_b', 'b@test.local', 'worker-b', 'B', 'runtime', true)"
    )
    backfill_default_mcp_connectors_and_grants(mcp_db)
    backfill_default_mcp_connectors_and_grants(mcp_db)
    count = mcp_db.execute(
        "SELECT COUNT(*) FROM main.admin_mcp_connectors WHERE connector_id = 'mcp_remote_http_oauth'"
    ).fetchone()[0]
    assert int(count) == 1
