"""Typed command handlers for DuckDB write operations.

Each handler receives a DuckDB connection (with active transaction) and the
command payload dict. Handlers do NOT manage transactions — the caller
(db-writer or inline executor) wraps them in BEGIN/COMMIT/ROLLBACK.

Extension pattern for vertical packages::

    # my_vertical/write_handlers.py
    from duckclaw.write_handlers.registry import register_handler

    def _apply_my_command(conn, payload: dict) -> None:
        ...

    register_handler("my_command", _apply_my_command)

Import the module from your package ``__init__`` (or from a bootstrap hook) so
registration runs at load time. Do not edit this dispatcher for new commands.

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

from duckclaw.write_handlers.registry import register_handler, registered_handlers

# Domain modules self-register handlers at import time.
from duckclaw.write_handlers import (  # noqa: F401
    access,
    admin_auth,
    duckdb_maintenance,
    hitl,
    kanban,
    knowledge,
    prompt_policies,
    raw_sql,
    runtime,
    usage_logs,
    workers,
    workspace,
    reports,
)
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
from duckclaw.write_handlers.hitl import (
    _apply_resolve_uncertainty_event,
    _apply_update_code_decision_status,
)
from duckclaw.write_handlers.prompt_policies import (
    _apply_deactivate_prompt_policy,
    _apply_restore_framework_policy_pack,
    _apply_sync_catalog_prompts,
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
from duckclaw.write_handlers.raw_sql import _apply_raw_sql
from duckclaw.write_handlers.usage_logs import (
    _apply_append_llm_usage_log,
    _apply_append_media_usage_log,
)
from duckclaw.write_handlers.workers import (
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
from duckclaw.write_handlers.workspace import (
    _apply_add_project_member,
    _apply_assign_agent_to_project,
    _apply_confirm_workspace_managed_draft,
    _apply_create_project,
    _apply_delete_project,
    _apply_detach_agent_from_project,
    _apply_set_project_status,
)

__all__ = [
    "dispatch_command",
    "register_handler",
]


def dispatch_command(conn: Any, payload: dict) -> None:
    """Route command_type to the appropriate handler.

    Raises ValueError for unknown command types.
    """
    command_type = str(payload.get("command_type") or "").strip()
    if not command_type:
        raise ValueError("command_type required")

    handler = registered_handlers().get(command_type)
    if handler is None:
        raise ValueError(f"Unknown command_type: {command_type}")

    handler(conn, payload)
