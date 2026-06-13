"""Tests for typed write commands and idempotency (phase-2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def db_with_migrations():
    import duckdb
    import tempfile

    from duckclaw.schema_migrations import run_pending_migrations

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "test.duckdb"))
    run_pending_migrations(con)

    con.execute(
        "INSERT INTO main.admin_console_users (email, nombre, rol, password_hash) "
        "VALUES ('test@d.local', 'Test', 'admin', 'hash')"
    )
    con.execute(
        "INSERT INTO main.admin_user_profiles (email, tenant_id) "
        "VALUES ('test@d.local', 'default')"
    )
    yield con
    con.close()


class TestWriteCommands:
    """Command model serialization tests."""

    def test_raw_sql_command_to_payload(self) -> None:
        from duckclaw.write_commands import RawSqlCommand

        cmd = RawSqlCommand(
            task_id="t1", query="SELECT 1", db_path="/tmp/test.duckdb",
            user_id="u1", tenant_id="default",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "raw_sql"
        assert raw["query"] == "SELECT 1"
        assert raw["task_id"] == "t1"

    def test_upsert_worker_command_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertWorkerCommand

        cmd = UpsertWorkerCommand(
            worker_id="test-w",
            display_name="Test Worker",
            actor_email="test@d.local",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "upsert_worker"
        assert raw["worker_id"] == "test-w"

    def test_create_project_command_roundtrip(self) -> None:
        from duckclaw.write_commands import CreateProjectCommand

        cmd = CreateProjectCommand(
            project_id="p1", name="Test Project", actor_email="test@d.local",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "create_project"
        assert raw["project_id"] == "p1"

    def test_upsert_runtime_setting_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertRuntimeSettingCommand

        cmd = UpsertRuntimeSettingCommand(
            domain="telegram", key="webhook_url",
            value="https://example.com",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "upsert_runtime_setting"
        assert raw["domain"] == "telegram"

    def test_kanban_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import DeleteKanbanCardCommand, UpsertKanbanCardCommand

        upsert = UpsertKanbanCardCommand(
            card_id="card_1",
            title="Crear agente",
            description="Desde tablero",
            status="todo",
            worker_id="default",
            tags=["manual"],
            actor_email="test@d.local",
        )
        raw = json.loads(upsert.to_redis_payload())
        assert raw["command_type"] == "upsert_kanban_card"
        assert raw["card_id"] == "card_1"
        assert raw["worker_id"] == "default"
        assert raw["tags"] == ["manual"]

        delete = DeleteKanbanCardCommand(card_id="card_1", actor_email="test@d.local")
        raw_delete = json.loads(delete.to_redis_payload())
        assert raw_delete["command_type"] == "delete_kanban_card"
        assert raw_delete["card_id"] == "card_1"

    def test_knowledge_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import (
            CreateKnowledgeSourceCommand,
            DeactivateKnowledgeSourceCommand,
            UpsertKnowledgeChunksCommand,
            UpsertKnowledgeDocumentCommand,
        )

        source = CreateKnowledgeSourceCommand(
            source_id="ksrc_1",
            tenant_id="tenant_a",
            actor_email="test@d.local",
            project_id="proj_a",
            source_kind="folder",
            source_uri="/safe/docs",
            display_name="Docs",
        )
        raw_source = json.loads(source.to_redis_payload())
        assert raw_source["command_type"] == "create_knowledge_source"
        assert raw_source["source_id"] == "ksrc_1"
        assert raw_source["project_id"] == "proj_a"

        document = UpsertKnowledgeDocumentCommand(
            document_id="kdoc_1",
            source_id="ksrc_1",
            relative_path="aws/iam.md",
            checksum="sha256:abc",
        )
        raw_document = json.loads(document.to_redis_payload())
        assert raw_document["command_type"] == "upsert_knowledge_document"
        assert raw_document["relative_path"] == "aws/iam.md"

        chunks = UpsertKnowledgeChunksCommand(
            document_id="kdoc_1",
            source_id="ksrc_1",
            chunks=[
                {"chunk_id": "kchk_1", "chunk_index": 0, "content": "IAM policies", "embedding_status": "PENDING"}
            ],
        )
        raw_chunks = json.loads(chunks.to_redis_payload())
        assert raw_chunks["command_type"] == "upsert_knowledge_chunks"
        assert raw_chunks["chunks"][0]["chunk_id"] == "kchk_1"

        delete = DeactivateKnowledgeSourceCommand(source_id="ksrc_1")
        raw_delete = json.loads(delete.to_redis_payload())
        assert raw_delete["command_type"] == "deactivate_knowledge_source"
        assert raw_delete["source_id"] == "ksrc_1"

    def test_prompt_policy_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import DeactivatePromptPolicyCommand, UpsertPromptPolicyCommand

        upsert = UpsertPromptPolicyCommand(
            policy_type="system_prompt",
            policy_name="rag_turn",
            version=2,
            content="Policy body created by the test.",
            metadata={"scope": "rag"},
            actor_email="test@d.local",
        )
        raw_upsert = json.loads(upsert.to_redis_payload())
        assert raw_upsert["command_type"] == "upsert_prompt_policy"
        assert raw_upsert["policy_type"] == "system_prompt"
        assert raw_upsert["policy_name"] == "rag_turn"
        assert raw_upsert["version"] == 2
        assert raw_upsert["content"] == "Policy body created by the test."
        assert raw_upsert["metadata"] == {"scope": "rag"}

        deactivate = DeactivatePromptPolicyCommand(
            policy_type="system_prompt",
            policy_name="rag_turn",
            version=2,
            actor_email="test@d.local",
        )
        raw_deactivate = json.loads(deactivate.to_redis_payload())
        assert raw_deactivate["command_type"] == "deactivate_prompt_policy"
        assert raw_deactivate["policy_type"] == "system_prompt"
        assert raw_deactivate["policy_name"] == "rag_turn"
        assert raw_deactivate["version"] == 2

    def test_each_command_has_unique_task_id(self) -> None:
        from duckclaw.write_commands import UpsertWorkerCommand

        c1 = UpsertWorkerCommand(worker_id="a", display_name="A")
        c2 = UpsertWorkerCommand(worker_id="b", display_name="B")
        assert c1.task_id != c2.task_id


class TestCommandHandlers:
    """Test that typed commands produce expected DB changes."""

    def test_upsert_worker_inserts(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "test-worker",
            "display_name": "Test",
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        row = con.execute(
            "SELECT worker_id, display_name FROM main.admin_worker_catalog "
            "WHERE tenant_id = 'default' AND worker_id = 'test-worker'"
        ).fetchone()
        assert row[0] == "test-worker"
        assert row[1] == "Test"

    def test_upsert_worker_updates_existing(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "test-w2",
            "display_name": "Old Name",
            "tenant_id": "default",
        })
        _apply_upsert_worker(con, {
            "worker_id": "test-w2",
            "display_name": "New Name",
            "tenant_id": "default",
        })
        row = con.execute(
            "SELECT display_name FROM main.admin_worker_catalog "
            "WHERE worker_id = 'test-w2' AND tenant_id = 'default'"
        ).fetchone()
        assert row[0] == "New Name"

    def test_deactivate_worker(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_worker, _apply_deactivate_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "to-delete",
            "display_name": "To Delete",
            "tenant_id": "default",
        })
        _apply_deactivate_worker(con, {
            "worker_id": "to-delete",
            "tenant_id": "default",
        })
        row = con.execute(
            "SELECT active, status FROM main.admin_worker_catalog "
            "WHERE worker_id = 'to-delete'"
        ).fetchone()
        assert row[0] == 0
        assert row[1] == "inactive"

    def test_create_project(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_create_project

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "proj-1",
            "name": "Alpha",
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        row = con.execute(
            "SELECT name, status FROM main.admin_projects WHERE project_id = 'proj-1'"
        ).fetchone()
        assert row[0] == "Alpha"
        assert row[1] == "active"

    def test_upsert_runtime_setting_with_actor_scope(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_runtime_setting

        con = db_with_migrations
        # Actor A sets a value
        _apply_upsert_runtime_setting(con, {
            "domain": "gateway", "key": "theme", "value": "dark",
            "tenant_id": "default", "actor_email": "alice@d.local",
        })
        # Actor B sets a different value for the same key
        _apply_upsert_runtime_setting(con, {
            "domain": "gateway", "key": "theme", "value": "light",
            "tenant_id": "default", "actor_email": "bob@d.local",
        })
        # Both should exist independently
        rows = con.execute(
            "SELECT actor_email, value_text FROM main.admin_runtime_settings "
            "WHERE domain = 'gateway' AND key = 'theme' ORDER BY actor_email"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "alice@d.local"
        assert rows[0][1] == "dark"
        assert rows[1][0] == "bob@d.local"
        assert rows[1][1] == "light"

    def test_upsert_kanban_card_inserts_updates_and_records_events(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_kanban_card

        con = db_with_migrations
        _apply_upsert_kanban_card(con, {
            "card_id": "card-k1",
            "title": "Primera",
            "description": "Crear worker",
            "status": "todo",
            "worker_id": "default",
            "tags": ["manual"],
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        _apply_upsert_kanban_card(con, {
            "card_id": "card-k1",
            "title": "Primera editada",
            "description": "Crear worker",
            "status": "in_progress",
            "worker_id": "default",
            "tags": ["manual", "db-first"],
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })

        row = con.execute(
            "SELECT title, status, assignee_email, tags_json FROM main.admin_kanban_cards "
            "WHERE card_id = 'card-k1'"
        ).fetchone()
        assert row[0] == "Primera editada"
        assert row[1] == "in_progress"
        assert row[2] == "default"
        assert json.loads(row[3]) == ["manual", "db-first"]

        events = con.execute(
            "SELECT event_type FROM main.admin_kanban_events "
            "WHERE card_id = 'card-k1' ORDER BY created_at"
        ).fetchall()
        assert [e[0] for e in events] == ["kanban_card.created", "kanban_card.updated"]

    def test_delete_kanban_card_scoped_to_actor(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_delete_kanban_card, _apply_upsert_kanban_card

        con = db_with_migrations
        _apply_upsert_kanban_card(con, {
            "card_id": "card-k2",
            "title": "Borrar",
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })

        with pytest.raises(ValueError, match="Kanban card not found"):
            _apply_delete_kanban_card(con, {
                "card_id": "card-k2",
                "tenant_id": "default",
                "actor_email": "other@d.local",
            })

        _apply_delete_kanban_card(con, {
            "card_id": "card-k2",
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        row = con.execute("SELECT card_id FROM main.admin_kanban_cards WHERE card_id = 'card-k2'").fetchone()
        assert row is None

    def test_knowledge_source_document_chunks_and_deactivate(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_create_knowledge_source,
            _apply_deactivate_knowledge_source,
            _apply_upsert_knowledge_chunks,
            _apply_upsert_knowledge_document,
        )

        con = db_with_migrations
        _apply_create_knowledge_source(con, {
            "source_id": "ksrc-handler",
            "tenant_id": "tenant_a",
            "actor_email": "test@d.local",
            "project_id": "proj_a",
            "worker_uid": "wrk_a",
            "source_kind": "folder",
            "source_uri": "/safe/docs",
            "display_name": "Docs",
            "metadata": {"domain": "aws"},
        })
        _apply_create_knowledge_source(con, {
            "source_id": "ksrc-handler",
            "tenant_id": "tenant_a",
            "actor_email": "test@d.local",
            "project_id": "proj_a",
            "worker_uid": "wrk_a",
            "source_kind": "folder",
            "source_uri": "/safe/docs-renamed",
            "display_name": "Docs v2",
        })
        row = con.execute(
            "SELECT source_uri, display_name, status FROM main.admin_knowledge_sources "
            "WHERE source_id = 'ksrc-handler'"
        ).fetchone()
        assert row == ("/safe/docs-renamed", "Docs v2", "pending")

        _apply_upsert_knowledge_document(con, {
            "document_id": "kdoc-handler",
            "source_id": "ksrc-handler",
            "relative_path": "aws/iam.md",
            "title": "IAM",
            "mime_type": "text/markdown",
            "checksum": "sha256:abc",
            "byte_size": 42,
            "metadata": {"section": "security"},
        })
        _apply_upsert_knowledge_chunks(con, {
            "document_id": "kdoc-handler",
            "source_id": "ksrc-handler",
            "tenant_id": "tenant_a",
            "project_id": "proj_a",
            "worker_uid": "wrk_a",
            "chunks": [
                {
                    "chunk_id": "kchk-handler-1",
                    "chunk_index": 0,
                    "content": "IAM policies and least privilege",
                    "content_hash": "hash-1",
                    "embedding_status": "PENDING",
                },
                {
                    "chunk_id": "kchk-handler-2",
                    "chunk_index": 1,
                    "content": "CloudTrail auditing",
                    "content_hash": "hash-2",
                    "embedding": [0.0] * 384,
                    "embedding_status": "READY",
                },
            ],
        })
        chunks = con.execute(
            "SELECT chunk_index, embedding_status FROM main.admin_knowledge_chunks "
            "WHERE document_id = 'kdoc-handler' ORDER BY chunk_index"
        ).fetchall()
        assert chunks == [(0, "PENDING"), (1, "READY")]

        _apply_deactivate_knowledge_source(con, {
            "source_id": "ksrc-handler",
            "tenant_id": "tenant_a",
        })
        active = con.execute(
            "SELECT active, status FROM main.admin_knowledge_sources WHERE source_id = 'ksrc-handler'"
        ).fetchone()
        assert active == (False, "inactive")
        chunk_active = con.execute(
            "SELECT DISTINCT active FROM main.admin_knowledge_chunks WHERE source_id = 'ksrc-handler'"
        ).fetchall()
        assert chunk_active == [(False,)]

    def test_prompt_policy_handler_upserts_updates_and_deactivates(self, db_with_migrations) -> None:
        from duckclaw.prompt_policies import PromptPolicyResolver
        from duckclaw.write_command_handlers import (
            _apply_deactivate_prompt_policy,
            _apply_upsert_prompt_policy,
            dispatch_command,
        )

        con = db_with_migrations
        _apply_upsert_prompt_policy(con, {
            "policy_type": "system_prompt",
            "policy_name": "rag_turn",
            "version": 1,
            "content": "Worker {worker_id} uses DB policy.",
            "metadata": {"scope": "rag"},
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        assert PromptPolicyResolver(db=con).format(
            "system_prompt",
            "rag_turn",
            worker_id="alpha",
        ) == "Worker alpha uses DB policy."

        dispatch_command(con, {
            "command_type": "upsert_prompt_policy",
            "policy_type": "system_prompt",
            "policy_name": "rag_turn",
            "version": 1,
            "content": "Updated {worker_id} DB policy.",
            "metadata": {"scope": "rag", "updated": True},
            "tenant_id": "default",
            "actor_email": "test@d.local",
        })
        row = con.execute(
            "SELECT content, metadata_json, active, status FROM main.prompt_policy_registry "
            "WHERE policy_type = 'system_prompt' AND policy_name = 'rag_turn' AND version = 1"
        ).fetchone()
        assert row[0] == "Updated {worker_id} DB policy."
        assert json.loads(row[1]) == {"scope": "rag", "updated": True}
        assert row[2] is True
        assert row[3] == "active"
        assert PromptPolicyResolver(db=con).format(
            "system_prompt",
            "rag_turn",
            worker_id="beta",
        ) == "Updated beta DB policy."

        _apply_deactivate_prompt_policy(con, {
            "policy_type": "system_prompt",
            "policy_name": "rag_turn",
            "version": 1,
            "tenant_id": "default",
        })
        inactive = con.execute(
            "SELECT active, status FROM main.prompt_policy_registry "
            "WHERE policy_type = 'system_prompt' AND policy_name = 'rag_turn' AND version = 1"
        ).fetchone()
        assert inactive == (False, "inactive")
        with pytest.raises(FileNotFoundError, match="active prompt policy not found"):
            PromptPolicyResolver(db=con).load("system_prompt", "rag_turn")

    def test_add_project_member(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_create_project,
            _apply_add_project_member,
        )

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "proj-addm", "name": "Add Member Test",
            "tenant_id": "default",
        })
        _apply_add_project_member(con, {
            "project_id": "proj-addm", "member_email": "member@d.local",
            "role": "viewer",
        })
        row = con.execute(
            "SELECT role FROM main.admin_project_members "
            "WHERE project_id = 'proj-addm' AND email = 'member@d.local'"
        ).fetchone()
        assert row[0] == "viewer"

    def test_assign_agent_to_project(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_create_project,
            _apply_upsert_worker,
            _apply_assign_agent_to_project,
        )

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "proj-agent", "name": "Agent Test",
            "tenant_id": "default",
        })
        _apply_upsert_worker(con, {
            "worker_id": "agent-w", "display_name": "Agent W",
            "tenant_id": "default",
        })
        wuid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id='agent-w'"
        ).fetchone()[0]

        _apply_assign_agent_to_project(con, {
            "project_id": "proj-agent", "worker_uid": wuid,
            "role": "viewer", "sort_order": 1,
        })
        row = con.execute(
            "SELECT role, sort_order FROM main.admin_project_agents "
            "WHERE project_id = 'proj-agent' AND worker_uid = ?", [wuid]
        ).fetchone()
        assert row[0] == "viewer"
        assert row[1] == 1

    def test_dispatch_unknown_command_type(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        with pytest.raises(ValueError, match="Unknown command_type"):
            dispatch_command(con, {"command_type": "nonexistent"})

    def test_raw_sql_skips_typed_handler(self) -> None:
        """RawSqlCommand command_type='raw_sql' so _handle_typed_command returns False."""
        from duckclaw.write_commands import RawSqlCommand

        cmd = RawSqlCommand(
            query="SELECT 1", db_path="/tmp/test.duckdb",
            user_id="u1", task_id="t-raw",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "raw_sql"
        # Typed handler skips raw_sql — falls through to legacy SQL path

    def test_write_ledger_records_entry(self, db_with_migrations) -> None:
        """admin_write_ledger INSERT and SELECT work correctly."""
        con = db_with_migrations
        con.execute(
            "INSERT INTO main.admin_write_ledger "
            "(task_id, command_type, command_json, status, created_at) "
            "VALUES ('ledger-t3', 'upsert_worker', '{}', 'completed', CURRENT_TIMESTAMP)"
        )
        row = con.execute(
            "SELECT status FROM main.admin_write_ledger WHERE task_id = 'ledger-t3'"
        ).fetchone()
        assert row[0] == "completed"

    def test_upsert_worker_unique_uid_per_tenant(self, db_with_migrations) -> None:
        """Two tenants with same worker_id get different worker_uid (no PK collision)."""
        from duckclaw.write_command_handlers import _apply_upsert_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "shared-name",
            "display_name": "Tenant A Worker",
            "tenant_id": "tenant-a",
        })
        _apply_upsert_worker(con, {
            "worker_id": "shared-name",
            "display_name": "Tenant B Worker",
            "tenant_id": "tenant-b",
        })
        rows = con.execute(
            "SELECT tenant_id, worker_uid FROM main.admin_worker_catalog "
            "WHERE worker_id = 'shared-name' ORDER BY tenant_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] != rows[1][1]  # Different worker_uid

    def test_upsert_worker_creates_version(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "versioned-w",
            "display_name": "Versioned",
            "tenant_id": "default",
            "manifest_snapshot": {"id": "v1", "skills": ["read_sql"]},
            "files_snapshot": {"system_prompt.md": "Be helpful."},
        })
        rows = con.execute(
            "SELECT version, manifest_snapshot_json, files_snapshot_json "
            "FROM main.admin_worker_versions "
            "WHERE worker_uid IN (SELECT worker_uid FROM main.admin_worker_catalog "
            "WHERE worker_id = 'versioned-w')"
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0][1] is not None  # manifest_snapshot_json populated

    def test_upsert_worker_creates_context(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_upsert_worker

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "ctx-w",
            "display_name": "Context Worker",
            "tenant_id": "default",
            "system_prompt": "You are helpful.",
        })
        rows = con.execute(
            "SELECT title, content_md FROM main.admin_worker_contexts "
            "WHERE worker_uid IN (SELECT worker_uid FROM main.admin_worker_catalog "
            "WHERE worker_id = 'ctx-w')"
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == "system_prompt"

    def test_create_project_assigns_agents(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_upsert_worker,
            _apply_create_project,
        )

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "proj-agent-1", "display_name": "PA1",
            "tenant_id": "default",
        })
        _apply_upsert_worker(con, {
            "worker_id": "proj-agent-2", "display_name": "PA2",
            "tenant_id": "default",
        })
        uid1 = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id='proj-agent-1'"
        ).fetchone()[0]
        uid2 = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id='proj-agent-2'"
        ).fetchone()[0]

        _apply_create_project(con, {
            "project_id": "proj-with-agents",
            "name": "Project With Agents",
            "tenant_id": "default",
            "agent_worker_uids": [uid1, uid2],
        })
        rows = con.execute(
            "SELECT worker_uid FROM main.admin_project_agents "
            "WHERE project_id = 'proj-with-agents' ORDER BY worker_uid"
        ).fetchall()
        assert len(rows) == 2
        assigned = {rows[0][0], rows[1][0]}
        assert uid1 in assigned
        assert uid2 in assigned

    def test_create_project_unknown_agent_raises(self, db_with_migrations) -> None:
        """assigning a non-existent worker_uid must raise ValueError."""
        from duckclaw.write_command_handlers import _apply_create_project

        con = db_with_migrations
        with pytest.raises(ValueError, match="Worker not found"):
            _apply_create_project(con, {
                "project_id": "proj-bad-agent",
                "name": "Bad Agent",
                "tenant_id": "default",
                "agent_worker_uids": ["nonexistent-uid"],
            })

    def test_add_project_member_nonexistent_project_raises(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_add_project_member

        con = db_with_migrations
        with pytest.raises(ValueError, match="Project not found"):
            _apply_add_project_member(con, {
                "project_id": "ghost-proj",
                "member_email": "user@d.local",
            })

    def test_assign_agent_nonexistent_project_raises(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_assign_agent_to_project

        con = db_with_migrations
        with pytest.raises(ValueError, match="Project not found"):
            _apply_assign_agent_to_project(con, {
                "project_id": "ghost-proj",
                "worker_uid": "whatever",
            })

    def test_assign_agent_nonexistent_worker_raises(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_create_project, _apply_assign_agent_to_project

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "orphan-proj", "name": "Orphan Test", "tenant_id": "default",
        })
        with pytest.raises(ValueError, match="Worker not found"):
            _apply_assign_agent_to_project(con, {
                "project_id": "orphan-proj",
                "worker_uid": "nonexistent-uid",
            })


class TestEnqueueTypedCommand:
    """Tests for enqueue_typed_command enrichment and validation."""

    def test_typed_writers_apply_migrations_before_write_ledger(self) -> None:
        db_queue = Path("packages/shared/src/duckclaw/db_write_queue.py").read_text(encoding="utf-8")
        db_writer = Path("services/db-writer/main.py").read_text(encoding="utf-8")

        assert "run_pending_migrations(conn)" in db_queue
        assert db_queue.index("run_pending_migrations(conn)") < db_queue.index("BEGIN TRANSACTION")
        assert "run_pending_migrations(conn)" in db_writer
        assert db_writer.index("run_pending_migrations(conn)") < db_writer.index("BEGIN TRANSACTION")

    def test_enqueue_typed_command_pushes_enriched_payload_once(self, monkeypatch) -> None:
        import sys
        import types

        from duckclaw.write_commands import UpsertWorkerCommand
        from duckclaw.db_write_queue import enqueue_typed_command

        lpush_calls: list[tuple[str, str]] = []

        class FakeRedisClient:
            def lpush(self, queue_name: str, payload: str) -> int:
                lpush_calls.append((queue_name, payload))
                return 1

        fake_redis = types.SimpleNamespace(
            from_url=lambda *_args, **_kwargs: FakeRedisClient(),
        )
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
        monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

        cmd = UpsertWorkerCommand(
            worker_id="enqueue-test", display_name="Enqueue T",
            tenant_id="default",
        )
        task_id = enqueue_typed_command(
            cmd,
            db_path="db/private/default/test.duckdb",
            user_id="test-user",
            queue_name="typed:q",
        )

        assert task_id == cmd.task_id
        assert len(lpush_calls) == 1
        queue_name, raw_payload = lpush_calls[0]
        enriched = json.loads(raw_payload)
        assert queue_name == "typed:q"
        assert enriched["db_path"] == "db/private/default/test.duckdb"
        assert enriched["user_id"] == "test-user"
        assert enriched["tenant_id"] == "default"
        assert enriched["task_id"] == cmd.task_id

    def test_assign_agent_rejects_cross_tenant_worker(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_assign_agent_to_project,
            _apply_create_project,
            _apply_upsert_worker,
        )

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "tenant-a-project",
            "name": "Tenant A",
            "tenant_id": "tenant-a",
        })
        _apply_upsert_worker(con, {
            "worker_id": "tenant-b-worker",
            "display_name": "Tenant B Worker",
            "tenant_id": "tenant-b",
        })
        worker_uid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog "
            "WHERE tenant_id = 'tenant-b' AND worker_id = 'tenant-b-worker'"
        ).fetchone()[0]

        with pytest.raises(ValueError, match="Worker tenant mismatch"):
            _apply_assign_agent_to_project(con, {
                "project_id": "tenant-a-project",
                "worker_uid": worker_uid,
            })

        rows = con.execute(
            "SELECT COUNT(*) FROM main.admin_project_agents "
            "WHERE project_id = 'tenant-a-project'"
        ).fetchone()
        assert rows[0] == 0
