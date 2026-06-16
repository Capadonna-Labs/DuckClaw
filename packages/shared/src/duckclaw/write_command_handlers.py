"""Typed command handlers for DuckDB write operations.

Each handler receives a DuckDB connection (with active transaction) and the
command payload dict. Handlers do NOT manage transactions — the caller
(db-writer or inline executor) wraps them in BEGIN/COMMIT/ROLLBACK.

Usage::

    from duckclaw.write_command_handlers import dispatch_command

    conn = duckdb.connect(path, read_only=False)
    conn.execute("BEGIN TRANSACTION")
    try:
        dispatch_command(conn, payload)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
"""
from __future__ import annotations

from typing import Any

from duckclaw.write_handlers.admin_auth import (
    _apply_clear_admin_login_failures,
    _apply_deactivate_console_user,
    _apply_record_admin_login_failure,
    _apply_update_console_user_password_hash,
    _apply_upsert_console_user,
)
from duckclaw.write_handlers.access import (
    _apply_delete_authorized_user,
    _apply_delete_shared_db_grant,
    _apply_upsert_authorized_user,
    _apply_upsert_shared_db_grant,
)
from duckclaw.write_handlers.kanban import (
    _apply_delete_kanban_card,
    _apply_upsert_kanban_card,
)
from duckclaw.write_handlers.knowledge import (
    _apply_create_knowledge_source,
    _apply_deactivate_knowledge_source,
    _apply_upsert_knowledge_chunks,
    _apply_upsert_knowledge_document,
)
from duckclaw.write_handlers.duckdb_maintenance import _apply_drop_legacy_duckdb_objects
from duckclaw.write_handlers.prompt_policies import (
    _apply_deactivate_prompt_policy,
    _apply_upsert_prompt_policy,
)
from duckclaw.write_handlers.runtime import (
    _apply_append_task_audit,
    _apply_delete_agent_config_entries,
    _apply_forget_chat_state,
    _apply_upsert_agent_config_entries,
    _apply_upsert_runtime_setting,
    _ensure_task_audit_log_table,
)
def dispatch_command(conn: Any, payload: dict) -> None:
    """Route command_type to the appropriate handler.

    Raises ValueError for unknown command types.
    """
    command_type = str(payload.get("command_type") or "").strip()
    if not command_type:
        raise ValueError("command_type required")

    handlers = {
        "upsert_worker": _apply_upsert_worker,
        "upsert_user_agent": _apply_upsert_user_agent,
        "upsert_catalog_skill": _apply_upsert_catalog_skill,
        "deactivate_catalog_skill": _apply_deactivate_catalog_skill,
        "deactivate_worker": _apply_deactivate_worker,
        "update_catalog_worker_file": _apply_update_catalog_worker_file,
        "deactivate_catalog_worker": _apply_deactivate_catalog_worker,
        "reactivate_catalog_worker": _apply_reactivate_catalog_worker,
        "hard_delete_catalog_worker": _apply_hard_delete_catalog_worker,
        "import_templates_to_catalog": _apply_import_templates_to_catalog,
        "upsert_worker_context": _apply_upsert_worker_context,
        "reorder_worker_contexts": _apply_reorder_worker_contexts,
        "deactivate_worker_context": _apply_deactivate_worker_context,
        "upsert_worker_capability": _apply_upsert_worker_capability,
        "create_project": _apply_create_project,
        "add_project_member": _apply_add_project_member,
        "assign_agent_to_project": _apply_assign_agent_to_project,
        "set_project_status": _apply_set_project_status,
        "delete_project": _apply_delete_project,
        "detach_agent_from_project": _apply_detach_agent_from_project,
        "confirm_workspace_managed_draft": _apply_confirm_workspace_managed_draft,
        "upsert_runtime_setting": _apply_upsert_runtime_setting,
        "upsert_agent_config_entries": _apply_upsert_agent_config_entries,
        "delete_agent_config_entries": _apply_delete_agent_config_entries,
        "forget_chat_state": _apply_forget_chat_state,
        "append_task_audit": _apply_append_task_audit,
        "upsert_console_user": _apply_upsert_console_user,
        "deactivate_console_user": _apply_deactivate_console_user,
        "record_admin_login_failure": _apply_record_admin_login_failure,
        "clear_admin_login_failures": _apply_clear_admin_login_failures,
        "update_console_user_password_hash": _apply_update_console_user_password_hash,
        "upsert_authorized_user": _apply_upsert_authorized_user,
        "delete_authorized_user": _apply_delete_authorized_user,
        "upsert_shared_db_grant": _apply_upsert_shared_db_grant,
        "delete_shared_db_grant": _apply_delete_shared_db_grant,
        "upsert_kanban_card": _apply_upsert_kanban_card,
        "delete_kanban_card": _apply_delete_kanban_card,
        "create_knowledge_source": _apply_create_knowledge_source,
        "upsert_knowledge_document": _apply_upsert_knowledge_document,
        "upsert_knowledge_chunks": _apply_upsert_knowledge_chunks,
        "deactivate_knowledge_source": _apply_deactivate_knowledge_source,
        "upsert_prompt_policy": _apply_upsert_prompt_policy,
        "deactivate_prompt_policy": _apply_deactivate_prompt_policy,
        "drop_legacy_duckdb_objects": _apply_drop_legacy_duckdb_objects,
    }
    handler = handlers.get(command_type)
    if handler is None:
        raise ValueError(f"Unknown command_type: {command_type}")

    handler(conn, payload)


# Canonical worker/catalog handlers live in duckclaw.write_handlers.workers.
# Keep these legacy names exported from this module for existing callers while
# making dispatch resolve to the SOA owner at call time.
from duckclaw.write_handlers.workers import (  # noqa: E402
    _apply_deactivate_catalog_skill,
    _apply_deactivate_catalog_worker,
    _apply_deactivate_worker,
    _apply_deactivate_worker_context,
    _apply_hard_delete_catalog_worker,
    _apply_import_templates_to_catalog,
    _apply_reactivate_catalog_worker,
    _apply_reorder_worker_contexts,
    _apply_update_catalog_worker_file,
    _apply_upsert_catalog_skill,
    _apply_upsert_user_agent,
    _apply_upsert_worker,
    _apply_upsert_worker_capability,
    _apply_upsert_worker_context,
    _resolve_worker_uid,
)
from duckclaw.write_handlers.workspace import (  # noqa: E402
    _apply_add_project_member,
    _apply_assign_agent_to_project,
    _apply_confirm_workspace_managed_draft,
    _apply_create_project,
    _apply_delete_project,
    _apply_detach_agent_from_project,
    _apply_set_project_status,
)
