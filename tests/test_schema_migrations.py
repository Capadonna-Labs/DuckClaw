"""Tests for versioned schema migrations (phase-1)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_migrations_create_expected_tables() -> None:
    """run_pending_migrations() creates schema_migrations + all generic versions."""
    import duckdb
    import tempfile

    from duckclaw.schema_migrations import (
        run_pending_migrations,
        verify_migration_integrity,
    )

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))

    applied = run_pending_migrations(con)
    assert len(applied) == 27, f"Expected 27 migrations, got {len(applied)}: {applied}"

    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    tables = {r[0] for r in rows}

    expected = {
        "schema_migrations",
        "admin_console_users",
        "admin_user_profiles",
        "admin_user_agents",
        "admin_worker_catalog",
        "admin_worker_versions",
        "admin_worker_contexts",
        "admin_worker_assignments",
        "admin_skills",
        "admin_worker_skills",
        "admin_capabilities",
        "admin_worker_capabilities",
        "admin_projects",
        "admin_project_members",
        "admin_project_agents",
        "admin_runtime_settings",
        "admin_resource_events",
        "admin_resource_tags",
        "admin_secret_refs",
        "user_shared_db_access",
        "admin_write_ledger",
        "admin_conversations",
        "admin_conversation_messages",
        "admin_conversation_artifacts",
        "admin_kanban_cards",
        "admin_kanban_events",
        "admin_workflows",
        "admin_workflow_versions",
        "admin_visual_assets",
        "admin_tool_servers",
        "admin_tool_bindings",
        "admin_tool_policies",
        "admin_knowledge_sources",
        "admin_knowledge_documents",
        "admin_knowledge_chunks",
        "prompt_policy_registry",
        "worker_prompt_bindings",
        "tool_policy_directives",
        "worker_runtime_policies",
        "admin_mcp_connectors",
        "admin_worker_mcp_grants",
    }
    missing = expected - tables
    assert not missing, f"Missing tables: {missing}"

    schemas = {
        r[0]
        for r in con.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
    }
    assert "war_room_core" not in schemas

    assert verify_migration_integrity(con) == []

    con.close()


def test_rag_knowledge_tables_have_key_columns_and_constraints() -> None:
    """RAG transversal tables support source/document/chunk lifecycle."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)

    cols = _columns(con, "admin_knowledge_sources")
    for c in (
        "source_id",
        "tenant_id",
        "project_id",
        "worker_uid",
        "source_kind",
        "source_uri",
        "status",
        "embedding_model",
        "metadata_json",
        "active",
    ):
        assert c in cols, f"admin_knowledge_sources missing {c}"

    cols = _columns(con, "admin_knowledge_documents")
    for c in (
        "document_id",
        "source_id",
        "relative_path",
        "title",
        "mime_type",
        "checksum",
        "metadata_json",
        "active",
    ):
        assert c in cols, f"admin_knowledge_documents missing {c}"

    cols = _columns(con, "admin_knowledge_chunks")
    for c in (
        "chunk_id",
        "document_id",
        "chunk_index",
        "content",
        "embedding",
        "embedding_status",
        "embedding_model",
        "token_count",
        "active",
    ):
        assert c in cols, f"admin_knowledge_chunks missing {c}"

    con.execute(
        """
        INSERT INTO main.admin_knowledge_sources
          (source_id, tenant_id, source_kind, source_uri, status, metadata_json)
        VALUES ('src_1', 'tenant_a', 'folder', '/tmp/docs', 'ready', '{"label":"docs"}')
        """
    )
    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            """
            INSERT INTO main.admin_knowledge_sources
              (source_id, tenant_id, source_kind, source_uri, status)
            VALUES ('src_bad_status', 'tenant_a', 'folder', '/tmp/docs', 'bogus')
            """
        )
    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            """
            INSERT INTO main.admin_knowledge_sources
              (source_id, tenant_id, source_kind, source_uri, metadata_json)
            VALUES ('src_bad_json', 'tenant_a', 'folder', '/tmp/docs', 'not-json')
            """
        )

    con.close()


def test_migrations_are_idempotent() -> None:
    """Second run applies zero migrations."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))

    run_pending_migrations(con)
    second = run_pending_migrations(con)

    assert second == [], f"Second run applied migrations: {second}"
    con.close()


def test_migration_atomicity_rollback_on_failure(monkeypatch) -> None:
    """Broken migration DDL causes rollback — no version recorded, no partial DDL applied."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import (
        _ALL_MIGRATIONS,
        applied_versions,
        run_pending_migrations,
    )

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))

    # Inject a broken migration at version 99
    broken_ddl = [
        # First DDL works (creates a table)
        "CREATE TABLE IF NOT EXISTS main.test_atomic (id INTEGER PRIMARY KEY)",
        # Second DDL is invalid — this should cause rollback
        "CREATE BROKEN SYNTAX !!!",
    ]
    monkeypatch.setattr(
        "duckclaw.schema_migrations._ALL_MIGRATIONS",
        [(99, "test_broken", broken_ddl)],
    )

    # Run pending — expect exception
    errored = False
    try:
        run_pending_migrations(con)
    except Exception:
        errored = True
    assert errored, "Broken migration should raise an exception"

    # Version 99 must NOT be registered
    versions = applied_versions(con)
    assert 99 not in versions, "Version 99 should NOT be registered after failure"

    # The partial DDL (CREATE TABLE test_atomic) must NOT exist
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }
    assert "test_atomic" not in tables, (
        "Table test_atomic should NOT exist after rollback"
    )

    con.close()


def test_admin_user_agents_ddl_allows_insert() -> None:
    """Migration DDL creates admin_user_agents compatible with INSERT (no agent_uid required)."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.admin_user_profiles import ensure_admin_user_profiles_table
    from duckclaw.admin_console_users import ensure_admin_console_users_table
    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))

    run_pending_migrations(con)

    # Seed the minimal dependencies
    ensure_admin_console_users_table(con)
    ensure_admin_user_profiles_table(con)
    con.execute(
        "INSERT INTO main.admin_console_users (email, nombre, rol, password_hash) "
        "VALUES ('test@d.local', 'Test', 'admin', 'hash')"
    )
    con.execute(
        "INSERT INTO main.admin_user_profiles (email, tenant_id) "
        "VALUES ('test@d.local', 'default')"
    )

    # Insert must succeed — no NOT NULL constraint on agent_uid
    con.execute(
        "INSERT INTO main.admin_user_agents "
        "(tenant_id, owner_email, worker_id, display_name, source_template_id, manifest_path, active) "
        "VALUES ('default', 'test@d.local', 'test-worker', 'Test Worker', 'default', '/tmp/x.yaml', true)"
    )

    rows = con.execute(
        "SELECT worker_id FROM main.admin_user_agents WHERE tenant_id='default'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "test-worker"

    con.close()


def test_drift_detected() -> None:
    """verify_migration_integrity() detects checksum mismatch."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import (
        _ALL_MIGRATIONS,
        _checksum,
        run_pending_migrations,
        verify_migration_integrity,
    )

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))

    run_pending_migrations(con)
    assert verify_migration_integrity(con) == []

    # Corrupt the registered checksum for version 1
    con.execute(
        "UPDATE main.schema_migrations SET checksum = 'corrupted' WHERE version = 1"
    )
    drifts = verify_migration_integrity(con)
    assert len(drifts) == 1
    assert "version=1" in drifts[0]
    assert "corrupted" in drifts[0]
    con.close()


def test_admin_write_ledger_has_expected_columns() -> None:
    """admin_write_ledger must have task_id, command_type, command_json, status."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)

    cols = {
        str(r[0])
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name='admin_write_ledger'"
        ).fetchall()
    }
    for required in ("task_id", "command_type", "command_json", "status"):
        assert required in cols, f"admin_write_ledger missing column: {required}"

    con.close()


def test_phase4_tables_have_key_columns() -> None:
    """Verify Phase 4 tables have required columns and constraints."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)

    # admin_conversations
    cols = _columns(con, "admin_conversations")
    for c in ("conversation_id", "tenant_id", "actor_email", "title"):
        assert c in cols, f"admin_conversations missing {c}"

    # admin_conversation_messages
    cols = _columns(con, "admin_conversation_messages")
    for c in ("message_id", "conversation_id", "role", "content"):
        assert c in cols

    # admin_conversation_artifacts
    cols = _columns(con, "admin_conversation_artifacts")
    for c in ("artifact_id", "conversation_id", "file_type", "file_path"):
        assert c in cols

    # admin_kanban_cards
    cols = _columns(con, "admin_kanban_cards")
    for c in ("card_id", "title", "status", "priority"):
        assert c in cols

    # admin_kanban_events
    cols = _columns(con, "admin_kanban_events")
    for c in ("event_id", "card_id", "event_type"):
        assert c in cols

    # admin_workflows
    cols = _columns(con, "admin_workflows")
    for c in ("workflow_id", "name", "category"):
        assert c in cols

    # admin_workflow_versions
    cols = _columns(con, "admin_workflow_versions")
    for c in ("workflow_id", "version", "workflow_json"):
        assert c in cols

    # admin_visual_assets
    cols = _columns(con, "admin_visual_assets")
    for c in ("asset_id", "request_json", "status"):
        assert c in cols

    # admin_tool_servers
    cols = _columns(con, "admin_tool_servers")
    for c in ("server_id", "name", "transport", "env_public_json"):
        assert c in cols, f"admin_tool_servers missing {c}"

    # admin_tool_bindings
    cols = _columns(con, "admin_tool_bindings")
    for c in ("binding_id", "server_id", "worker_uid", "tools_csv"):
        assert c in cols

    # admin_tool_policies
    cols = _columns(con, "admin_tool_policies")
    for c in ("policy_id", "worker_uid", "tool_name", "allow_network"):
        assert c in cols

    con.close()


def test_phase4_check_constraints_reject_invalid() -> None:
    """Verify CHECK constraints on Phase 4 tables reject bad values."""
    import duckdb
    import tempfile
    from pathlib import Path

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)

    # kanban_cards.status CHECK ('todo','in_progress','done','cancelled')
    con.execute(
        "INSERT INTO main.admin_kanban_cards (card_id, title, status) VALUES ('k1', 'Test', 'todo')"
    )
    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            "INSERT INTO main.admin_kanban_cards (card_id, title, status) VALUES ('k2', 'Bad', 'invalid_status')"
        )

    # visual_assets.status CHECK ('pending','generating','completed','failed')
    con.execute(
        "INSERT INTO main.admin_visual_assets (asset_id, request_json, status) "
        "VALUES ('a1', '{}', 'pending')"
    )
    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            "INSERT INTO main.admin_visual_assets (asset_id, request_json, status) "
            "VALUES ('a2', '{}', 'bogus')"
        )

    # tool_servers.transport CHECK ('stdio','http','docker')
    con.execute(
        "INSERT INTO main.admin_tool_servers (server_id, name, transport) VALUES ('s1', 'Test', 'stdio')"
    )
    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            "INSERT INTO main.admin_tool_servers (server_id, name, transport) VALUES ('s2', 'Bad', 'invalid')"
        )

    # tool_servers.env_public_json accepts valid JSON (no secret leak)
    con.execute(
        "UPDATE main.admin_tool_servers SET env_public_json = '{\"label\": \"test\"}' WHERE server_id = 's1'"
    )
    row = con.execute(
        "SELECT env_public_json FROM main.admin_tool_servers WHERE server_id = 's1'"
    ).fetchone()
    assert '"label"' in row[0]

    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            "UPDATE main.admin_tool_servers SET env_public_json = 'not-json' WHERE server_id = 's1'"
        )

    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            "UPDATE main.admin_tool_servers SET env_public_json = '{\"api_key\": \"secret\"}' "
            "WHERE server_id = 's1'"
        )

    con.close()


def _columns(con, table: str) -> set[str]:
    return {
        str(r[0])
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name=?",
            [table],
        ).fetchall()
    }
