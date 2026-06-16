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

import json
import uuid
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


def _json_metadata(raw: Any) -> str:
    data = raw if isinstance(raw, dict) else {}
    return json.dumps(data, ensure_ascii=False, default=str)


def _require_knowledge_source(conn: Any, source_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT tenant_id, project_id, worker_uid, active FROM main.admin_knowledge_sources "
        "WHERE source_id = ?",
        [source_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Knowledge source not found: {source_id}")
    return {
        "tenant_id": str(row[0] or "default"),
        "project_id": str(row[1] or ""),
        "worker_uid": str(row[2] or ""),
        "active": bool(row[3]),
    }


def _apply_create_knowledge_source(conn: Any, payload: dict) -> None:
    source_id = str(payload["source_id"]).strip()
    if not source_id:
        raise ValueError("source_id required")
    tenant_id = str(payload.get("tenant_id", "default") or "default").strip() or "default"
    actor_email = str(payload.get("actor_email", "system") or "system").strip() or "system"
    project_id = str(payload.get("project_id") or "").strip()
    worker_uid = str(payload.get("worker_uid") or "").strip()
    source_kind = str(payload.get("source_kind") or "folder").strip()
    source_uri = str(payload.get("source_uri") or "").strip()
    if not source_uri:
        raise ValueError("source_uri required")
    display_name = str(payload.get("display_name") or "").strip()
    status = str(payload.get("status") or "pending").strip()
    embedding_model = str(
        payload.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
    ).strip()
    embedding_dim = int(payload.get("embedding_dim") or 384)
    metadata_json = _json_metadata(payload.get("metadata"))

    existing = conn.execute(
        "SELECT source_id FROM main.admin_knowledge_sources WHERE source_id = ?",
        [source_id],
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.admin_knowledge_sources "
            "SET tenant_id = ?, actor_email = ?, project_id = ?, worker_uid = ?, "
            "source_kind = ?, source_uri = ?, display_name = ?, status = ?, "
            "embedding_model = ?, embedding_dim = ?, metadata_json = ?, active = true, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE source_id = ?",
            [
                tenant_id,
                actor_email,
                project_id,
                worker_uid,
                source_kind,
                source_uri,
                display_name,
                status,
                embedding_model,
                embedding_dim,
                metadata_json,
                source_id,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_knowledge_sources "
            "(source_id, tenant_id, actor_email, project_id, worker_uid, source_kind, "
            "source_uri, display_name, status, embedding_model, embedding_dim, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                source_id,
                tenant_id,
                actor_email,
                project_id,
                worker_uid,
                source_kind,
                source_uri,
                display_name,
                status,
                embedding_model,
                embedding_dim,
                metadata_json,
            ],
        )


def _apply_upsert_knowledge_document(conn: Any, payload: dict) -> None:
    document_id = str(payload["document_id"]).strip()
    source_id = str(payload["source_id"]).strip()
    relative_path = str(payload["relative_path"]).strip().lstrip("/")
    checksum = str(payload["checksum"]).strip()
    if not document_id or not source_id or not relative_path or not checksum:
        raise ValueError("document_id, source_id, relative_path and checksum required")
    _require_knowledge_source(conn, source_id)
    title = str(payload.get("title") or "").strip()
    mime_type = str(payload.get("mime_type") or "text/plain").strip() or "text/plain"
    byte_size = int(payload.get("byte_size") or 0)
    metadata_json = _json_metadata(payload.get("metadata"))

    existing = conn.execute(
        "SELECT document_id FROM main.admin_knowledge_documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.admin_knowledge_documents "
            "SET source_id = ?, relative_path = ?, title = ?, mime_type = ?, checksum = ?, "
            "byte_size = ?, metadata_json = ?, active = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE document_id = ?",
            [source_id, relative_path, title, mime_type, checksum, byte_size, metadata_json, document_id],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_knowledge_documents "
            "(document_id, source_id, relative_path, title, mime_type, checksum, byte_size, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [document_id, source_id, relative_path, title, mime_type, checksum, byte_size, metadata_json],
        )


def _normalize_embedding(raw: Any) -> list[float] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 384:
        raise ValueError("embedding must be a 384-dim list")
    out: list[float] = []
    for value in raw:
        if not isinstance(value, (int, float)):
            raise ValueError("embedding values must be numeric")
        out.append(float(value))
    return out


def _apply_upsert_knowledge_chunks(conn: Any, payload: dict) -> None:
    document_id = str(payload["document_id"]).strip()
    source_id = str(payload["source_id"]).strip()
    if not document_id or not source_id:
        raise ValueError("document_id and source_id required")
    source = _require_knowledge_source(conn, source_id)
    doc = conn.execute(
        "SELECT document_id FROM main.admin_knowledge_documents "
        "WHERE document_id = ? AND source_id = ?",
        [document_id, source_id],
    ).fetchone()
    if not doc:
        raise ValueError(f"Knowledge document not found: {document_id}")

    tenant_id = str(payload.get("tenant_id") or source["tenant_id"] or "default").strip() or "default"
    project_id = str(payload.get("project_id") or source["project_id"] or "").strip()
    worker_uid = str(payload.get("worker_uid") or source["worker_uid"] or "").strip()
    chunks = payload.get("chunks") or []
    if not isinstance(chunks, list):
        raise ValueError("chunks must be a list")

    conn.execute(
        "UPDATE main.admin_knowledge_chunks SET active = false, updated_at = CURRENT_TIMESTAMP "
        "WHERE document_id = ?",
        [document_id],
    )
    for item in chunks:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or f"kchk_{uuid.uuid4().hex[:16]}").strip()
        chunk_index = int(item.get("chunk_index") or 0)
        content = str(item.get("content") or "").strip()
        if not chunk_id or not content:
            continue
        content_hash = str(item.get("content_hash") or "").strip() or f"idx:{chunk_index}:{len(content)}"
        status = str(item.get("embedding_status") or "PENDING").strip().upper()
        embedding = _normalize_embedding(item.get("embedding"))
        if embedding is not None:
            status = "READY"
        if status not in {"PENDING", "READY", "FAILED"}:
            raise ValueError(f"Invalid embedding_status: {status}")
        metadata_json = _json_metadata(item.get("metadata"))
        token_count = int(item.get("token_count") or max(1, len(content.split())))
        start_offset = int(item.get("start_offset") or 0)
        end_offset = int(item.get("end_offset") or 0)
        embedding_model = str(
            item.get("embedding_model") or payload.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
        )

        existing = conn.execute(
            "SELECT chunk_id FROM main.admin_knowledge_chunks WHERE chunk_id = ?",
            [chunk_id],
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE main.admin_knowledge_chunks "
                "SET document_id = ?, source_id = ?, tenant_id = ?, project_id = ?, worker_uid = ?, "
                "chunk_index = ?, content = ?, content_hash = ?, start_offset = ?, end_offset = ?, "
                "token_count = ?, embedding = ?, embedding_status = ?, embedding_model = ?, "
                "metadata_json = ?, active = true, updated_at = CURRENT_TIMESTAMP "
                "WHERE chunk_id = ?",
                [
                    document_id,
                    source_id,
                    tenant_id,
                    project_id,
                    worker_uid,
                    chunk_index,
                    content,
                    content_hash,
                    start_offset,
                    end_offset,
                    token_count,
                    embedding,
                    status,
                    embedding_model,
                    metadata_json,
                    chunk_id,
                ],
            )
        else:
            conn.execute(
                "INSERT INTO main.admin_knowledge_chunks "
                "(chunk_id, document_id, source_id, tenant_id, project_id, worker_uid, chunk_index, "
                "content, content_hash, start_offset, end_offset, token_count, embedding, "
                "embedding_status, embedding_model, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    chunk_id,
                    document_id,
                    source_id,
                    tenant_id,
                    project_id,
                    worker_uid,
                    chunk_index,
                    content,
                    content_hash,
                    start_offset,
                    end_offset,
                    token_count,
                    embedding,
                    status,
                    embedding_model,
                    metadata_json,
                ],
            )


def _apply_deactivate_knowledge_source(conn: Any, payload: dict) -> None:
    source_id = str(payload["source_id"]).strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    row = conn.execute(
        "SELECT source_id FROM main.admin_knowledge_sources "
        "WHERE source_id = ? AND tenant_id = ?",
        [source_id, tenant_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Knowledge source not found: {source_id}")
    conn.execute(
        "UPDATE main.admin_knowledge_sources "
        "SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP "
        "WHERE source_id = ?",
        [source_id],
    )
    conn.execute(
        "UPDATE main.admin_knowledge_documents "
        "SET active = false, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?",
        [source_id],
    )
    conn.execute(
        "UPDATE main.admin_knowledge_chunks "
        "SET active = false, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?",
        [source_id],
    )


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
