"""Tests for typed write commands and idempotency (phase-2)."""
from __future__ import annotations

import inspect
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

    def test_upsert_worker_capability_command_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertWorkerCapabilityCommand

        cmd = UpsertWorkerCapabilityCommand(
            worker_id="analytics-reader",
            capability_name="bounded_select_star_read",
            actor_email="test@d.local",
            policy={"reason": "protect unbounded table reads"},
        )
        raw = json.loads(cmd.to_redis_payload())

        assert raw["command_type"] == "upsert_worker_capability"
        assert raw["worker_id"] == "analytics-reader"
        assert raw["capability_name"] == "bounded_select_star_read"
        assert raw["kind"] == "runtime_policy"
        assert raw["policy"] == {"reason": "protect unbounded table reads"}

    def test_create_project_command_roundtrip(self) -> None:
        from duckclaw.write_commands import CreateProjectCommand

        cmd = CreateProjectCommand(
            project_id="p1", name="Test Project", actor_email="test@d.local",
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "create_project"
        assert raw["project_id"] == "p1"

    def test_workspace_project_mutation_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import (
            DeleteProjectCommand,
            DetachAgentFromProjectCommand,
            SetProjectStatusCommand,
        )

        status_cmd = SetProjectStatusCommand(
            project_id="p1",
            status="inactive",
            actor_email="owner@d.local",
        )
        delete_cmd = DeleteProjectCommand(project_id="p1", actor_email="owner@d.local")
        detach_cmd = DetachAgentFromProjectCommand(
            project_id="p1",
            worker_uid="wrk_1",
            actor_email="owner@d.local",
        )

        assert json.loads(status_cmd.to_redis_payload())["command_type"] == "set_project_status"
        assert json.loads(status_cmd.to_redis_payload())["status"] == "inactive"
        assert json.loads(delete_cmd.to_redis_payload())["command_type"] == "delete_project"
        assert json.loads(detach_cmd.to_redis_payload())["command_type"] == "detach_agent_from_project"
        assert json.loads(detach_cmd.to_redis_payload())["worker_uid"] == "wrk_1"

    def test_confirm_workspace_managed_draft_command_roundtrip(self) -> None:
        from duckclaw.write_commands import ConfirmWorkspaceManagedDraftCommand

        cmd = ConfirmWorkspaceManagedDraftCommand(
            task_id="task-managed-confirm-1",
            tenant_id="default",
            actor_email="test@d.local",
            project_id="prj_managed_1",
            project_name="Soporte Tickets",
            project_description="Atiende casos con datos de soporte",
            workers=[
                {
                    "worker_id": "ticket-support-agent",
                    "display_name": "Ticket Support Agent",
                    "role": "member",
                    "system_prompt": "Ayuda a resolver casos usando contexto de soporte.",
                }
            ],
            shared_context="# Contexto soporte",
            suggested_skills=[{"name": "ticket_lookup", "available": True}],
            source_kind="managed_draft",
            context_title="Contexto compartido",
            change_note="Created from DB-first managed draft",
        )

        raw = json.loads(cmd.to_redis_payload())

        assert raw["command_type"] == "confirm_workspace_managed_draft"
        assert raw["task_id"] == "task-managed-confirm-1"
        assert raw["project_id"] == "prj_managed_1"
        assert raw["workers"][0]["worker_id"] == "ticket-support-agent"
        assert raw["source_kind"] == "managed_draft"

    def test_upsert_user_agent_command_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertUserAgentCommand

        cmd = UpsertUserAgentCommand(
            task_id="task-user-agent-1",
            tenant_id="default",
            actor_email="test@d.local",
            worker_uid="wrk_user_agent_1",
            worker_id="sales_bot",
            display_name="Sales Bot",
            source_template_id="default",
            system_prompt="Ayuda con ventas consultivas.",
            description="Agente creado desde la consola admin.",
            skills=["read_knowledge"],
        )

        raw = json.loads(cmd.to_redis_payload())

        assert raw["command_type"] == "upsert_user_agent"
        assert raw["task_id"] == "task-user-agent-1"
        assert raw["worker_uid"] == "wrk_user_agent_1"
        assert raw["worker_id"] == "sales_bot"
        assert raw["skills"] == ["read_knowledge"]

    def test_catalog_skill_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import DeactivateCatalogSkillCommand, UpsertCatalogSkillCommand

        upsert = UpsertCatalogSkillCommand(
            task_id="task-skill-1",
            tenant_id="default",
            actor_email="test@d.local",
            name="customer_lookup",
            description="Consulta datos de clientes desde una API controlada.",
            skill_type="python",
            implementation_ref="db://skills/customer_lookup.py",
            visibility="private",
        )
        deactivate = DeactivateCatalogSkillCommand(
            task_id="task-skill-delete-1",
            tenant_id="default",
            actor_email="test@d.local",
            name="customer_lookup",
        )

        raw_upsert = json.loads(upsert.to_redis_payload())
        raw_deactivate = json.loads(deactivate.to_redis_payload())

        assert raw_upsert["command_type"] == "upsert_catalog_skill"
        assert raw_upsert["name"] == "customer_lookup"
        assert raw_upsert["implementation_ref"] == "db://skills/customer_lookup.py"
        assert raw_upsert["visibility"] == "private"
        assert raw_deactivate["command_type"] == "deactivate_catalog_skill"
        assert raw_deactivate["name"] == "customer_lookup"

    def test_template_catalog_mutation_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import (
            DeactivateCatalogWorkerCommand,
            HardDeleteCatalogWorkerCommand,
            ReactivateCatalogWorkerCommand,
            UpdateCatalogWorkerFileCommand,
        )

        update_file = UpdateCatalogWorkerFileCommand(
            task_id="task-template-file-1",
            tenant_id="default",
            actor_email="test@d.local",
            worker_id="sales-helper",
            file_path="system_prompt.md",
            content="Ayuda al equipo con respuestas trazables.",
        )
        deactivate = DeactivateCatalogWorkerCommand(
            task_id="task-template-delete-1",
            tenant_id="default",
            actor_email="test@d.local",
            worker_id="sales-helper",
        )
        reactivate = ReactivateCatalogWorkerCommand(
            task_id="task-template-reactivate-1",
            tenant_id="default",
            actor_email="test@d.local",
            worker_id="sales-helper",
        )
        hard_delete = HardDeleteCatalogWorkerCommand(
            task_id="task-template-hard-delete-1",
            tenant_id="default",
            actor_email="test@d.local",
            worker_id="sales-helper",
        )

        raw_update = json.loads(update_file.to_redis_payload())
        raw_deactivate = json.loads(deactivate.to_redis_payload())
        raw_reactivate = json.loads(reactivate.to_redis_payload())
        raw_hard_delete = json.loads(hard_delete.to_redis_payload())

        assert raw_update["command_type"] == "update_catalog_worker_file"
        assert raw_update["worker_id"] == "sales-helper"
        assert raw_update["file_path"] == "system_prompt.md"
        assert raw_update["content"] == "Ayuda al equipo con respuestas trazables."
        assert raw_deactivate["command_type"] == "deactivate_catalog_worker"
        assert raw_reactivate["command_type"] == "reactivate_catalog_worker"
        assert raw_hard_delete["command_type"] == "hard_delete_catalog_worker"

    def test_drop_legacy_duckdb_objects_command_roundtrip(self) -> None:
        from duckclaw.write_commands import DropLegacyDuckDbObjectsCommand

        command = DropLegacyDuckDbObjectsCommand(
            task_id="task-drop-legacy-1",
            tenant_id="default",
            actor_email="test@d.local",
            user_id="owner123",
            db_path="/tmp/axis.duckdb",
            schemas=["cleanup_schema"],
            main_tables=["archived_default_orders"],
        )

        raw = json.loads(command.to_redis_payload())

        assert raw["command_type"] == "drop_legacy_duckdb_objects"
        assert raw["user_id"] == "owner123"
        assert raw["db_path"] == "/tmp/axis.duckdb"
        assert raw["schemas"] == ["cleanup_schema"]
        assert raw["main_tables"] == ["archived_default_orders"]

    def test_upsert_runtime_setting_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertRuntimeSettingCommand

        cmd = UpsertRuntimeSettingCommand(
            tenant_id="global",
            actor_email="admin@test.local",
            domain="telegram",
            key="webhook_routes",
            value="",
            value_kind="json",
            value_json={"routes": []},
            secret=True,
        )
        raw = json.loads(cmd.to_redis_payload())
        assert raw["command_type"] == "upsert_runtime_setting"
        assert raw["domain"] == "telegram"
        assert raw["tenant_id"] == "global"
        assert raw["actor_email"] == "admin@test.local"
        assert raw["value_json"] == {"routes": []}
        assert raw["secret"] is True

    def test_upsert_agent_config_entries_command_roundtrip(self) -> None:
        from duckclaw.write_commands import UpsertAgentConfigEntriesCommand

        cmd = UpsertAgentConfigEntriesCommand(
            tenant_id="tenant-a",
            actor_email="system",
            entries={
                "chat_42_goals_delta_seconds": "0",
                "chat_42_goals_proactive_anchor_epoch": "",
            },
        )

        raw = json.loads(cmd.to_redis_payload())

        assert raw["command_type"] == "upsert_agent_config_entries"
        assert raw["entries"]["chat_42_goals_delta_seconds"] == "0"

    def test_delete_agent_config_entries_command_roundtrip(self) -> None:
        from duckclaw.write_commands import DeleteAgentConfigEntriesCommand

        cmd = DeleteAgentConfigEntriesCommand(
            tenant_id="tenant-a",
            actor_email="system",
            keys=["chat_42_goals_delta_seconds", "chat_42_goals_cron_wall"],
        )

        raw = json.loads(cmd.to_redis_payload())

        assert raw["command_type"] == "delete_agent_config_entries"
        assert raw["keys"] == ["chat_42_goals_delta_seconds", "chat_42_goals_cron_wall"]

    def test_forget_chat_state_command_roundtrip(self) -> None:
        from duckclaw.write_commands import ForgetChatStateCommand

        telegram_cmd = ForgetChatStateCommand(
            tenant_id="tenant-a",
            actor_email="chat:12345",
            chat_id="12345",
        )
        api_cmd = ForgetChatStateCommand(
            tenant_id="tenant-a",
            actor_email="chat:default",
            chat_id="default",
        )

        raw_telegram = json.loads(telegram_cmd.to_redis_payload())
        raw_api = json.loads(api_cmd.to_redis_payload())

        assert raw_telegram["command_type"] == "forget_chat_state"
        assert raw_telegram["chat_id"] == "12345"
        assert raw_api["command_type"] == "forget_chat_state"
        assert raw_api["chat_id"] == "default"

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

    def test_authorized_user_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import DeleteAuthorizedUserCommand, UpsertAuthorizedUserCommand

        upsert = UpsertAuthorizedUserCommand(
            tenant_id="Orchestrator",
            actor_email="telegram:1",
            user_id="3",
            username="user3",
            role="admin",
        )
        raw_upsert = json.loads(upsert.to_redis_payload())
        assert raw_upsert["command_type"] == "upsert_authorized_user"
        assert raw_upsert["tenant_id"] == "Orchestrator"
        assert raw_upsert["user_id"] == "3"
        assert raw_upsert["username"] == "user3"
        assert raw_upsert["role"] == "admin"

        delete = DeleteAuthorizedUserCommand(
            tenant_id="Orchestrator",
            actor_email="telegram:1",
            user_id="3",
        )
        raw_delete = json.loads(delete.to_redis_payload())
        assert raw_delete["command_type"] == "delete_authorized_user"
        assert raw_delete["tenant_id"] == "Orchestrator"
        assert raw_delete["user_id"] == "3"

    def test_console_user_commands_roundtrip(self) -> None:
        from duckclaw.write_commands import (
            ClearAdminLoginFailuresCommand,
            DeactivateConsoleUserCommand,
            RecordAdminLoginFailureCommand,
            UpdateConsoleUserPasswordHashCommand,
            UpsertConsoleUserCommand,
        )

        upsert = UpsertConsoleUserCommand(
            actor_email="admin@test.local",
            email="viewer@test.local",
            nombre="Viewer",
            rol="user",
            password="viewpass",
            initials="VW",
            active=True,
        )
        raw_upsert = json.loads(upsert.to_redis_payload())
        assert raw_upsert["command_type"] == "upsert_console_user"
        assert raw_upsert["email"] == "viewer@test.local"
        assert raw_upsert["rol"] == "user"
        assert raw_upsert["password"] == "viewpass"

        deactivate = DeactivateConsoleUserCommand(
            actor_email="admin@test.local",
            email="viewer@test.local",
        )
        raw_deactivate = json.loads(deactivate.to_redis_payload())
        assert raw_deactivate["command_type"] == "deactivate_console_user"
        assert raw_deactivate["email"] == "viewer@test.local"

        failure = RecordAdminLoginFailureCommand(
            actor_email="admin@test.local",
            email="viewer@test.local",
        )
        clear = ClearAdminLoginFailuresCommand(
            actor_email="admin@test.local",
            email="viewer@test.local",
        )
        password_hash = UpdateConsoleUserPasswordHashCommand(
            actor_email="admin@test.local",
            email="viewer@test.local",
            password_hash="$argon2id$v=19$m=65536,t=2,p=4$abc$def",
            hash_algo="argon2id",
            hash_params={"time_cost": 2, "memory_cost": 65536, "parallelism": 4},
        )
        raw_failure = json.loads(failure.to_redis_payload())
        raw_clear = json.loads(clear.to_redis_payload())
        raw_password_hash = json.loads(password_hash.to_redis_payload())
        assert raw_failure["command_type"] == "record_admin_login_failure"
        assert raw_clear["command_type"] == "clear_admin_login_failures"
        assert raw_password_hash["command_type"] == "update_console_user_password_hash"
        assert raw_password_hash["hash_algo"] == "argon2id"
        assert raw_password_hash["hash_params"]["memory_cost"] == 65536

    def test_shared_access_commands_roundtrip_without_war_room_core(self) -> None:
        from duckclaw.write_commands import (
            DeleteSharedDbGrantCommand,
            UpsertSharedDbGrantCommand,
        )

        shared_upsert = UpsertSharedDbGrantCommand(
            tenant_id="Orchestrator",
            actor_email="telegram:1",
            user_id="77",
            resource_key="default",
        )
        raw_shared_upsert = json.loads(shared_upsert.to_redis_payload())
        assert raw_shared_upsert["command_type"] == "upsert_shared_db_grant"
        assert raw_shared_upsert["resource_key"] == "default"

        shared_delete = DeleteSharedDbGrantCommand(
            tenant_id="Orchestrator",
            actor_email="telegram:1",
            user_id="77",
            resource_key="default",
        )
        raw_shared_delete = json.loads(shared_delete.to_redis_payload())
        assert raw_shared_delete["command_type"] == "delete_shared_db_grant"
        assert raw_shared_delete["resource_key"] == "default"

    def test_war_room_is_not_a_shared_write_command_domain(self) -> None:
        import duckclaw.write_commands as write_commands

        removed_names = (
            "UpsertWarRoomMemberCommand",
            "DeleteWarRoomMemberCommand",
            "AppendWarRoomAuditCommand",
        )
        for name in removed_names:
            assert not hasattr(write_commands, name)

    def test_each_command_has_unique_task_id(self) -> None:
        from duckclaw.write_commands import UpsertWorkerCommand

        c1 = UpsertWorkerCommand(worker_id="a", display_name="A")
        c2 = UpsertWorkerCommand(worker_id="b", display_name="B")
        assert c1.task_id != c2.task_id


class TestCommandHandlers:
    """Test that typed commands produce expected DB changes."""

    def test_runtime_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import runtime as runtime_handlers

        handler_names = (
            "_apply_upsert_runtime_setting",
            "_apply_upsert_agent_config_entries",
            "_apply_delete_agent_config_entries",
            "_apply_forget_chat_state",
            "_ensure_task_audit_log_table",
            "_apply_append_task_audit",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(runtime_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.runtime"

        source = inspect.getsource(runtime_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_access_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import access as access_handlers

        handler_names = (
            "_apply_upsert_authorized_user",
            "_apply_delete_authorized_user",
            "_apply_upsert_shared_db_grant",
            "_apply_delete_shared_db_grant",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(access_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.access"

        source = inspect.getsource(access_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_worker_catalog_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import workers as worker_handlers

        handler_names = (
            "_apply_upsert_worker",
            "_apply_upsert_user_agent",
            "_apply_upsert_catalog_skill",
            "_apply_deactivate_catalog_skill",
            "_apply_deactivate_worker",
            "_apply_update_catalog_worker_file",
            "_apply_deactivate_catalog_worker",
            "_apply_reactivate_catalog_worker",
            "_apply_hard_delete_catalog_worker",
            "_apply_import_templates_to_catalog",
            "_apply_upsert_worker_context",
            "_apply_reorder_worker_contexts",
            "_apply_deactivate_worker_context",
            "_apply_upsert_worker_capability",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(worker_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.workers"

        source = inspect.getsource(worker_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_workspace_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import workspace as workspace_handlers

        handler_names = (
            "_apply_create_project",
            "_apply_add_project_member",
            "_apply_assign_agent_to_project",
            "_apply_set_project_status",
            "_apply_delete_project",
            "_apply_detach_agent_from_project",
            "_apply_confirm_workspace_managed_draft",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(workspace_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.workspace"

        source = inspect.getsource(workspace_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_kanban_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import kanban as kanban_handlers

        handler_names = (
            "_apply_upsert_kanban_card",
            "_apply_delete_kanban_card",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(kanban_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.kanban"

        source = inspect.getsource(kanban_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_admin_auth_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import admin_auth as admin_auth_handlers

        handler_names = (
            "_apply_upsert_console_user",
            "_apply_deactivate_console_user",
            "_apply_record_admin_login_failure",
            "_apply_clear_admin_login_failures",
            "_apply_update_console_user_password_hash",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(admin_auth_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.admin_auth"

        source = inspect.getsource(admin_auth_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_prompt_policy_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import prompt_policies as prompt_policy_handlers

        handler_names = (
            "_apply_upsert_prompt_policy",
            "_apply_deactivate_prompt_policy",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(prompt_policy_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.prompt_policies"

        source = inspect.getsource(prompt_policy_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_duckdb_maintenance_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import duckdb_maintenance as maintenance_handlers

        exported = getattr(write_command_handlers, "_apply_drop_legacy_duckdb_objects")
        canonical = getattr(maintenance_handlers, "_apply_drop_legacy_duckdb_objects")
        assert exported is canonical
        assert canonical.__module__ == "duckclaw.write_handlers.duckdb_maintenance"

        source = inspect.getsource(maintenance_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

    def test_knowledge_write_handlers_live_in_domain_module(self) -> None:
        from duckclaw import write_command_handlers
        from duckclaw.write_handlers import knowledge as knowledge_handlers

        handler_names = (
            "_apply_create_knowledge_source",
            "_apply_upsert_knowledge_document",
            "_apply_upsert_knowledge_chunks",
            "_apply_deactivate_knowledge_source",
        )

        for name in handler_names:
            exported = getattr(write_command_handlers, name)
            canonical = getattr(knowledge_handlers, name)
            assert exported is canonical
            assert canonical.__module__ == "duckclaw.write_handlers.knowledge"

        source = inspect.getsource(knowledge_handlers)
        assert "BEGIN TRANSACTION" not in source
        assert "COMMIT" not in source

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

    def test_upsert_runtime_setting_preserves_json_value(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_runtime_setting",
            "domain": "duckdb",
            "key": "legacy_schemas",
            "value": "",
            "value_kind": "json",
            "value_json": ["cleanup_schema"],
            "tenant_id": "default",
            "actor_email": "",
        })

        row = con.execute(
            "SELECT value_text, value_json, value_kind FROM main.admin_runtime_settings "
            "WHERE domain = 'duckdb' AND key = 'legacy_schemas'"
        ).fetchone()

        assert row[0] == ""
        assert json.loads(row[1]) == ["cleanup_schema"]
        assert row[2] == "json"

    def test_console_user_commands_apply_and_deactivate(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_console_user",
            "actor_email": "admin@test.local",
            "email": "ops@test.local",
            "nombre": "Ops",
            "rol": "user",
            "password": "ops-pass-123",
            "initials": "OP",
            "active": True,
        })
        row = con.execute(
            "SELECT email, nombre, rol, active FROM main.admin_console_users "
            "WHERE email = 'ops@test.local'"
        ).fetchone()
        assert row == ("ops@test.local", "Ops", "user", True)

        dispatch_command(con, {
            "command_type": "upsert_console_user",
            "actor_email": "admin@test.local",
            "email": "ops@test.local",
            "nombre": "Ops Renamed",
            "rol": "admin",
            "initials": "OR",
            "active": True,
        })
        updated = con.execute(
            "SELECT nombre, rol, initials, active FROM main.admin_console_users "
            "WHERE email = 'ops@test.local'"
        ).fetchone()
        assert updated == ("Ops Renamed", "admin", "OR", True)

        dispatch_command(con, {
            "command_type": "deactivate_console_user",
            "actor_email": "admin@test.local",
            "email": "ops@test.local",
        })
        active = con.execute(
            "SELECT active FROM main.admin_console_users WHERE email = 'ops@test.local'"
        ).fetchone()
        assert active == (False,)

    def test_admin_auth_state_commands_apply_idempotently(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_console_user",
            "actor_email": "admin@test.local",
            "email": "auth-state@test.local",
            "nombre": "Auth State",
            "rol": "admin",
            "password": "auth-pass-123",
            "initials": "AS",
            "active": True,
        })

        failure_payload = {
            "command_type": "record_admin_login_failure",
            "actor_email": "admin@test.local",
            "email": "auth-state@test.local",
        }
        dispatch_command(con, failure_payload)
        dispatch_command(con, failure_payload)
        failed = con.execute(
            "SELECT failed_login_count, last_failed_at IS NOT NULL "
            "FROM main.admin_console_users WHERE email = 'auth-state@test.local'"
        ).fetchone()
        assert failed == (2, True)

        password_payload = {
            "command_type": "update_console_user_password_hash",
            "actor_email": "admin@test.local",
            "email": "auth-state@test.local",
            "password_hash": "$argon2id$v=19$m=65536,t=2,p=4$abc$def",
            "hash_algo": "argon2id",
            "hash_params": {"time_cost": 2, "memory_cost": 65536, "parallelism": 4},
        }
        dispatch_command(con, password_payload)
        dispatch_command(con, password_payload)
        updated = con.execute(
            "SELECT password_hash, hash_algo, failed_login_count, last_failed_at "
            "FROM main.admin_console_users WHERE email = 'auth-state@test.local'"
        ).fetchone()
        assert updated == ("$argon2id$v=19$m=65536,t=2,p=4$abc$def", "argon2id", 0, None)

        dispatch_command(con, failure_payload)
        dispatch_command(con, {
            "command_type": "clear_admin_login_failures",
            "actor_email": "admin@test.local",
            "email": "auth-state@test.local",
        })
        cleared = con.execute(
            "SELECT failed_login_count, last_failed_at "
            "FROM main.admin_console_users WHERE email = 'auth-state@test.local'"
        ).fetchone()
        assert cleared == (0, None)

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

    def test_agent_config_entries_handler_upserts_idempotently(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        con.execute(
            "CREATE TABLE agent_config ("
            "key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        dispatch_command(con, {
            "command_type": "upsert_agent_config_entries",
            "entries": {
                "chat_42_goals_delta_seconds": "120",
                "chat_42_goals_cron_wall": '{"kind":"daily"}',
            },
        })
        dispatch_command(con, {
            "command_type": "upsert_agent_config_entries",
            "entries": {
                "chat_42_goals_delta_seconds": "0",
                "chat_42_goals_cron_wall": "",
            },
        })

        rows = con.execute(
            "SELECT key, value FROM agent_config "
            "WHERE key IN ('chat_42_goals_delta_seconds', 'chat_42_goals_cron_wall') "
            "ORDER BY key"
        ).fetchall()

        assert rows == [
            ("chat_42_goals_cron_wall", ""),
            ("chat_42_goals_delta_seconds", "0"),
        ]

    def test_agent_config_entries_handler_deletes_idempotently(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        con.execute(
            "CREATE TABLE agent_config ("
            "key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        dispatch_command(con, {
            "command_type": "upsert_agent_config_entries",
            "entries": {
                "chat_42_goals_delta_seconds": "120",
                "chat_42_goals_cron_wall": '{"kind":"daily"}',
            },
        })

        payload = {
            "command_type": "delete_agent_config_entries",
            "keys": ["chat_42_goals_delta_seconds", "chat_42_goals_delta_seconds"],
        }
        dispatch_command(con, payload)
        dispatch_command(con, payload)

        rows = con.execute("SELECT key, value FROM agent_config ORDER BY key").fetchall()

        assert rows == [("chat_42_goals_cron_wall", '{"kind":"daily"}')]

    def test_forget_chat_state_handler_deletes_conversations_and_audit_idempotently(
        self,
        db_with_migrations,
    ) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        con.execute(
            "CREATE TABLE IF NOT EXISTS telegram_conversation ("
            "chat_id BIGINT, role TEXT, content TEXT, received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS api_conversation ("
            "session_id VARCHAR, worker_id VARCHAR, role VARCHAR, content TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_config ("
            "key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute("INSERT INTO telegram_conversation (chat_id, role, content) VALUES (12345, 'user', 'hola')")
        con.execute(
            "INSERT INTO api_conversation (session_id, worker_id, role, content) "
            "VALUES ('default', 'manager', 'user', 'hola')"
        )
        con.execute("INSERT INTO agent_config (key, value) VALUES ('chat_12345_last_audit', '{\"latency_ms\": 1}')")
        con.execute("INSERT INTO agent_config (key, value) VALUES ('chat_default_last_audit', '{\"latency_ms\": 2}')")

        telegram_payload = {
            "command_type": "forget_chat_state",
            "tenant_id": "tenant-a",
            "actor_email": "chat:12345",
            "chat_id": "12345",
        }
        api_payload = {
            "command_type": "forget_chat_state",
            "tenant_id": "tenant-a",
            "actor_email": "chat:default",
            "chat_id": "default",
        }

        dispatch_command(con, telegram_payload)
        dispatch_command(con, telegram_payload)
        dispatch_command(con, api_payload)
        dispatch_command(con, api_payload)

        telegram_count = con.execute(
            "SELECT count(*) FROM telegram_conversation WHERE chat_id = 12345"
        ).fetchone()[0]
        api_count = con.execute(
            "SELECT count(*) FROM api_conversation WHERE session_id = 'default'"
        ).fetchone()[0]
        audit_rows = con.execute(
            "SELECT key, value FROM agent_config "
            "WHERE key IN ('chat_12345_last_audit', 'chat_default_last_audit') "
            "ORDER BY key"
        ).fetchall()

        assert telegram_count == 0
        assert api_count == 0
        assert audit_rows == []

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

    def test_worker_context_handlers_create_reorder_and_deactivate(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_worker",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "context-worker",
            "display_name": "Context Worker",
        })
        worker_uid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog "
            "WHERE tenant_id = 'default' AND worker_id = 'context-worker'"
        ).fetchone()[0]

        dispatch_command(con, {
            "command_type": "upsert_worker_context",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_uid": worker_uid,
            "title": "notes.md",
            "content_md": "# Notes",
            "sort_order": 30,
        })
        context_id = con.execute(
            "SELECT context_id FROM main.admin_worker_contexts "
            "WHERE worker_uid = ? AND title = 'notes.md' AND active = true",
            [worker_uid],
        ).fetchone()[0]

        dispatch_command(con, {
            "command_type": "reorder_worker_contexts",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_uid": worker_uid,
            "items": [{"context_id": context_id, "sort_order": 5}],
        })
        assert con.execute(
            "SELECT sort_order FROM main.admin_worker_contexts WHERE context_id = ?",
            [context_id],
        ).fetchone()[0] == 5

        dispatch_command(con, {
            "command_type": "deactivate_worker_context",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_uid": worker_uid,
            "context_id": context_id,
        })
        assert con.execute(
            "SELECT active FROM main.admin_worker_contexts WHERE context_id = ?",
            [context_id],
        ).fetchone()[0] is False

    def test_authorized_user_handlers_upsert_and_delete(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_authorized_user",
            "tenant_id": "Orchestrator",
            "actor_email": "telegram:1",
            "user_id": "3",
            "username": "user3",
            "role": "admin",
        })
        row = con.execute(
            "SELECT username, role FROM main.authorized_users "
            "WHERE tenant_id = 'Orchestrator' AND user_id = '3'"
        ).fetchone()
        assert row == ("user3", "admin")

        dispatch_command(con, {
            "command_type": "upsert_authorized_user",
            "tenant_id": "Orchestrator",
            "actor_email": "telegram:1",
            "user_id": "3",
            "username": "renamed",
            "role": "user",
        })
        row = con.execute(
            "SELECT username, role FROM main.authorized_users "
            "WHERE tenant_id = 'Orchestrator' AND user_id = '3'"
        ).fetchone()
        assert row == ("renamed", "user")

        dispatch_command(con, {
            "command_type": "delete_authorized_user",
            "tenant_id": "Orchestrator",
            "actor_email": "telegram:1",
            "user_id": "3",
        })
        deleted = con.execute(
            "SELECT user_id FROM main.authorized_users "
            "WHERE tenant_id = 'Orchestrator' AND user_id = '3'"
        ).fetchone()
        assert deleted is None

    def test_war_room_handlers_are_not_registered_in_shared_dispatcher(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        removed_command_types = (
            "upsert_war_room_member",
            "append_war_room_audit",
            "delete_war_room_member",
        )
        for command_type in removed_command_types:
            with pytest.raises(ValueError, match=f"Unknown command_type: {command_type}"):
                dispatch_command(
                    con,
                    {
                        "command_type": command_type,
                        "tenant_id": "wr_-1001",
                        "actor_email": "telegram:1",
                        "user_id": "77",
                    },
                )

    def test_shared_grant_handlers_upsert_and_delete(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_shared_db_grant",
            "tenant_id": "Orchestrator",
            "actor_email": "telegram:1",
            "user_id": "77",
            "resource_key": "default",
        })
        row = con.execute(
            "SELECT resource_key FROM main.user_shared_db_access "
            "WHERE tenant_id = 'Orchestrator' AND user_id = '77'"
        ).fetchone()
        assert row == ("default",)

        dispatch_command(con, {
            "command_type": "delete_shared_db_grant",
            "tenant_id": "Orchestrator",
            "actor_email": "telegram:1",
            "user_id": "77",
            "resource_key": "default",
        })
        deleted = con.execute(
            "SELECT resource_key FROM main.user_shared_db_access "
            "WHERE tenant_id = 'Orchestrator' AND user_id = '77'"
        ).fetchone()
        assert deleted is None

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

    def test_upsert_worker_capability_applies_and_is_idempotent(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_upsert_worker,
            _apply_upsert_worker_capability,
        )

        con = db_with_migrations
        _apply_upsert_worker(con, {
            "worker_id": "analytics-reader",
            "display_name": "Analytics Reader",
            "tenant_id": "default",
        })

        payload = {
            "worker_id": "analytics-reader",
            "tenant_id": "default",
            "capability_name": "bounded_select_star_read",
            "kind": "runtime_policy",
            "provider": "duckclaw",
            "permission": "use",
            "policy": {"reason": "protect unbounded table reads"},
        }
        _apply_upsert_worker_capability(con, payload)
        _apply_upsert_worker_capability(con, payload)

        rows = con.execute(
            """
            SELECT c.name, c.kind, wc.permission, wc.policy_json
            FROM main.admin_worker_capabilities wc
            JOIN main.admin_capabilities c ON c.capability_id = wc.capability_id
            JOIN main.admin_worker_catalog w ON w.worker_uid = wc.worker_uid
            WHERE w.worker_id = 'analytics-reader'
              AND c.name = 'bounded_select_star_read'
            """
        ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "bounded_select_star_read"
        assert rows[0][1] == "runtime_policy"
        assert rows[0][2] == "use"
        assert json.loads(rows[0][3]) == {"reason": "protect unbounded table reads"}

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

    def test_project_status_handler_is_idempotent_and_tenant_scoped(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import _apply_create_project, _apply_set_project_status

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "status-proj",
            "name": "Status Project",
            "tenant_id": "tenant-a",
            "actor_email": "owner@d.local",
        })

        payload = {
            "command_type": "set_project_status",
            "project_id": "status-proj",
            "tenant_id": "tenant-a",
            "actor_email": "owner@d.local",
            "status": "inactive",
        }
        _apply_set_project_status(con, payload)
        _apply_set_project_status(con, payload)

        row = con.execute(
            "SELECT status, active FROM main.admin_projects WHERE project_id = 'status-proj'",
        ).fetchone()
        assert row == ("inactive", True)
        with pytest.raises(ValueError, match="Project not found"):
            _apply_set_project_status(con, {**payload, "tenant_id": "tenant-b", "status": "active"})

    def test_delete_project_handler_removes_project_relations_for_tenant(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_create_project,
            _apply_delete_project,
            _apply_upsert_worker,
            _apply_assign_agent_to_project,
        )

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "delete-proj",
            "name": "Delete Project",
            "tenant_id": "tenant-a",
            "actor_email": "owner@d.local",
        })
        _apply_upsert_worker(con, {
            "worker_id": "delete-worker",
            "display_name": "Delete Worker",
            "tenant_id": "tenant-a",
        })
        worker_uid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id = 'delete-worker'",
        ).fetchone()[0]
        _apply_assign_agent_to_project(con, {
            "project_id": "delete-proj",
            "worker_uid": worker_uid,
            "tenant_id": "tenant-a",
            "actor_email": "owner@d.local",
        })

        _apply_delete_project(con, {
            "command_type": "delete_project",
            "project_id": "delete-proj",
            "tenant_id": "tenant-a",
            "actor_email": "owner@d.local",
        })

        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_projects WHERE project_id = 'delete-proj'",
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_project_agents WHERE project_id = 'delete-proj'",
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_project_members WHERE project_id = 'delete-proj'",
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_catalog WHERE worker_uid = ?",
            [worker_uid],
        ).fetchone()[0] == 1

    def test_detach_agent_handler_soft_deactivates_assignment_for_tenant(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import (
            _apply_assign_agent_to_project,
            _apply_create_project,
            _apply_detach_agent_from_project,
            _apply_upsert_worker,
        )

        con = db_with_migrations
        _apply_create_project(con, {
            "project_id": "detach-proj",
            "name": "Detach Project",
            "tenant_id": "tenant-a",
        })
        _apply_upsert_worker(con, {
            "worker_id": "detach-worker",
            "display_name": "Detach Worker",
            "tenant_id": "tenant-a",
        })
        worker_uid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id = 'detach-worker'",
        ).fetchone()[0]
        _apply_assign_agent_to_project(con, {
            "project_id": "detach-proj",
            "worker_uid": worker_uid,
        })

        payload = {
            "command_type": "detach_agent_from_project",
            "project_id": "detach-proj",
            "worker_uid": worker_uid,
            "tenant_id": "tenant-a",
        }
        _apply_detach_agent_from_project(con, payload)
        _apply_detach_agent_from_project(con, payload)

        row = con.execute(
            "SELECT active FROM main.admin_project_agents "
            "WHERE project_id = 'detach-proj' AND worker_uid = ?",
            [worker_uid],
        ).fetchone()
        assert row == (False,)

    def test_confirm_workspace_managed_draft_handler_is_idempotent(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        payload = {
            "command_type": "confirm_workspace_managed_draft",
            "command_version": 1,
            "task_id": "task-managed-confirm-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "project_id": "prj_managed_1",
            "project_name": "Soporte Tickets",
            "project_description": "Atiende casos con datos de soporte",
            "workers": [
                {
                    "worker_id": "ticket-support-agent",
                    "display_name": "Ticket Support Agent",
                    "role": "member",
                    "system_prompt": "Ayuda a resolver casos usando contexto de soporte.",
                }
            ],
            "shared_context": "# Contexto soporte\nUsar tono claro.",
            "suggested_skills": [{"name": "ticket_lookup", "reason": "consulta tickets", "available": True}],
            "source_kind": "managed_draft",
            "context_title": "Contexto compartido",
            "change_note": "Created from DB-first managed draft",
        }

        dispatch_command(con, payload)
        dispatch_command(con, payload)

        counts = {
            "projects": con.execute(
                "SELECT COUNT(*) FROM main.admin_projects WHERE project_id = 'prj_managed_1'"
            ).fetchone()[0],
            "workers": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_catalog "
                "WHERE tenant_id = 'default' AND worker_id = 'ticket-support-agent'"
            ).fetchone()[0],
            "versions": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_versions v "
                "JOIN main.admin_worker_catalog w ON w.worker_uid = v.worker_uid "
                "WHERE w.worker_id = 'ticket-support-agent'"
            ).fetchone()[0],
            "contexts": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_contexts c "
                "JOIN main.admin_worker_catalog w ON w.worker_uid = c.worker_uid "
                "WHERE w.worker_id = 'ticket-support-agent' AND c.title = 'Contexto compartido'"
            ).fetchone()[0],
            "assignments": con.execute(
                "SELECT COUNT(*) FROM main.admin_project_agents pa "
                "JOIN main.admin_worker_catalog w ON w.worker_uid = pa.worker_uid "
                "WHERE pa.project_id = 'prj_managed_1' AND w.worker_id = 'ticket-support-agent'"
            ).fetchone()[0],
        }
        row = con.execute(
            "SELECT p.name, wc.worker_id, pa.role, pa.sort_order "
            "FROM main.admin_projects p "
            "JOIN main.admin_project_agents pa ON pa.project_id = p.project_id "
            "JOIN main.admin_worker_catalog wc ON wc.worker_uid = pa.worker_uid "
            "WHERE p.project_id = 'prj_managed_1'"
        ).fetchone()
        files_snapshot = con.execute(
            "SELECT v.files_snapshot_json FROM main.admin_worker_versions v "
            "JOIN main.admin_worker_catalog w ON w.worker_uid = v.worker_uid "
            "WHERE w.worker_id = 'ticket-support-agent'"
        ).fetchone()[0]

        assert counts == {
            "projects": 1,
            "workers": 1,
            "versions": 1,
            "contexts": 1,
            "assignments": 1,
        }
        assert row == ("Soporte Tickets", "ticket-support-agent", "member", 0)
        assert json.loads(files_snapshot)["system_prompt.md"].startswith("Ayuda a resolver")

    def test_upsert_user_agent_handler_is_db_first_and_idempotent(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        payload = {
            "command_type": "upsert_user_agent",
            "command_version": 1,
            "task_id": "task-user-agent-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_uid": "wrk_user_agent_1",
            "worker_id": "sales_bot",
            "display_name": "Sales Bot",
            "source_template_id": "default",
            "system_prompt": "Ayuda con ventas consultivas.",
            "description": "Agente creado desde consola admin.",
            "skills": ["read_knowledge"],
        }

        dispatch_command(con, payload)
        dispatch_command(con, payload)

        worker = con.execute(
            "SELECT worker_uid, owner_email, display_name, source_kind, source_template_id "
            "FROM main.admin_worker_catalog WHERE tenant_id = 'default' AND worker_id = 'sales_bot'"
        ).fetchone()
        user_agent = con.execute(
            "SELECT owner_email, display_name, source_template_id, manifest_path "
            "FROM main.admin_user_agents WHERE tenant_id = 'default' AND worker_id = 'sales_bot'"
        ).fetchone()
        counts = {
            "workers": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_catalog "
                "WHERE tenant_id = 'default' AND worker_id = 'sales_bot'"
            ).fetchone()[0],
            "user_agents": con.execute(
                "SELECT COUNT(*) FROM main.admin_user_agents "
                "WHERE tenant_id = 'default' AND worker_id = 'sales_bot'"
            ).fetchone()[0],
            "versions": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_versions WHERE worker_uid = 'wrk_user_agent_1'"
            ).fetchone()[0],
            "contexts": con.execute(
                "SELECT COUNT(*) FROM main.admin_worker_contexts "
                "WHERE worker_uid = 'wrk_user_agent_1' AND title = 'system_prompt'"
            ).fetchone()[0],
        }
        files_snapshot = con.execute(
            "SELECT files_snapshot_json FROM main.admin_worker_versions WHERE worker_uid = 'wrk_user_agent_1'"
        ).fetchone()[0]

        assert worker == ("wrk_user_agent_1", "test@d.local", "Sales Bot", "runtime", "default")
        assert user_agent == (
            "test@d.local",
            "Sales Bot",
            "default",
            "db://admin_worker_catalog/wrk_user_agent_1/manifest.json",
        )
        assert counts == {"workers": 1, "user_agents": 1, "versions": 1, "contexts": 1}
        assert json.loads(files_snapshot)["manifest.json"].startswith("{")

    def test_catalog_skill_handler_upserts_and_deactivates_idempotently(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        payload = {
            "command_type": "upsert_catalog_skill",
            "command_version": 1,
            "task_id": "task-skill-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "name": "customer_lookup",
            "description": "Consulta datos de clientes desde una API controlada.",
            "skill_type": "python",
            "implementation_ref": "db://skills/customer_lookup.py",
            "visibility": "private",
        }

        dispatch_command(con, payload)
        dispatch_command(con, {**payload, "description": "Actualizada", "visibility": "public"})

        row = con.execute(
            "SELECT name, description, skill_type, implementation_ref, owner_email, tenant_id, "
            "visibility, active FROM main.admin_skills WHERE name = 'customer_lookup'"
        ).fetchone()
        count = con.execute(
            "SELECT COUNT(*) FROM main.admin_skills WHERE name = 'customer_lookup'"
        ).fetchone()[0]

        assert row == (
            "customer_lookup",
            "Actualizada",
            "python",
            "db://skills/customer_lookup.py",
            "test@d.local",
            "default",
            "public",
            True,
        )
        assert count == 1

        delete_payload = {
            "command_type": "deactivate_catalog_skill",
            "command_version": 1,
            "task_id": "task-skill-delete-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "name": "customer_lookup",
        }
        dispatch_command(con, delete_payload)
        dispatch_command(con, delete_payload)

        assert con.execute(
            "SELECT active FROM main.admin_skills WHERE name = 'customer_lookup'"
        ).fetchone()[0] is False

    def test_template_catalog_handlers_mutate_actor_owned_worker(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        dispatch_command(con, {
            "command_type": "upsert_worker",
            "command_version": 1,
            "task_id": "task-worker-template-owner",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "sales-helper",
            "display_name": "Sales Helper",
            "source_kind": "runtime",
        })
        worker_uid = con.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog WHERE worker_id = 'sales-helper'"
        ).fetchone()[0]

        dispatch_command(con, {
            "command_type": "update_catalog_worker_file",
            "command_version": 1,
            "task_id": "task-template-file-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "sales-helper",
            "file_path": "system_prompt.md",
            "content": "Responde con evidencia local.",
        })

        version_row = con.execute(
            "SELECT files_snapshot_json FROM main.admin_worker_versions "
            "WHERE worker_uid = ? ORDER BY version DESC LIMIT 1",
            [worker_uid],
        ).fetchone()
        context_row = con.execute(
            "SELECT content_md FROM main.admin_worker_contexts "
            "WHERE worker_uid = ? AND title = 'system_prompt.md' AND active = true",
            [worker_uid],
        ).fetchone()

        assert json.loads(version_row[0])["system_prompt.md"] == "Responde con evidencia local."
        assert context_row[0] == "Responde con evidencia local."

        dispatch_command(con, {
            "command_type": "deactivate_catalog_worker",
            "command_version": 1,
            "task_id": "task-template-delete-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "sales-helper",
        })
        assert con.execute(
            "SELECT active, status FROM main.admin_worker_catalog WHERE worker_uid = ?",
            [worker_uid],
        ).fetchone() == (False, "inactive")

        dispatch_command(con, {
            "command_type": "reactivate_catalog_worker",
            "command_version": 1,
            "task_id": "task-template-reactivate-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "sales-helper",
        })
        assert con.execute(
            "SELECT active, status FROM main.admin_worker_catalog WHERE worker_uid = ?",
            [worker_uid],
        ).fetchone() == (True, "active")

        dispatch_command(con, {
            "command_type": "hard_delete_catalog_worker",
            "command_version": 1,
            "task_id": "task-template-hard-delete-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "worker_id": "sales-helper",
        })
        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_catalog WHERE worker_uid = ?",
            [worker_uid],
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_contexts WHERE worker_uid = ?",
            [worker_uid],
        ).fetchone()[0] == 0

    def test_drop_legacy_duckdb_objects_handler_drops_requested_objects(self, db_with_migrations) -> None:
        from duckclaw.write_command_handlers import dispatch_command

        con = db_with_migrations
        con.execute("CREATE SCHEMA cleanup_schema")
        con.execute("CREATE TABLE cleanup_schema.legacy_table (id INTEGER)")
        con.execute("CREATE TABLE main.archived_default_orders (id INTEGER)")
        con.execute("CREATE TABLE main.keep_me (id INTEGER)")

        dispatch_command(con, {
            "command_type": "drop_legacy_duckdb_objects",
            "command_version": 1,
            "task_id": "task-drop-legacy-1",
            "tenant_id": "default",
            "actor_email": "test@d.local",
            "user_id": "default",
            "db_path": "",
            "schemas": ["cleanup_schema"],
            "main_tables": ["archived_default_orders"],
        })

        schemas = {
            row[0]
            for row in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
        }
        main_tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }

        assert "cleanup_schema" not in schemas
        assert "archived_default_orders" not in main_tables
        assert "keep_me" in main_tables


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

    def test_enqueue_typed_command_preserves_domain_user_id(self, monkeypatch) -> None:
        import sys
        import types

        from duckclaw.db_write_queue import enqueue_typed_command
        from duckclaw.write_commands import UpsertSharedDbGrantCommand

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

        cmd = UpsertSharedDbGrantCommand(
            tenant_id="tenant-a",
            actor_email="admin@test.local",
            user_id="target-user",
            resource_key="default",
        )
        task_id = enqueue_typed_command(
            cmd,
            db_path="db/private/default/test.duckdb",
            user_id="admin-actor",
            queue_name="typed:q",
        )

        assert task_id == cmd.task_id
        enriched = json.loads(lpush_calls[0][1])
        assert enriched["user_id"] == "target-user"
        assert enriched["db_write_user_id"] == "admin-actor"
        assert enriched["actor_email"] == "admin@test.local"

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
