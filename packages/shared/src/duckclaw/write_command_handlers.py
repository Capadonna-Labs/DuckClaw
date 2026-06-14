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

import hashlib
import json
import logging
import uuid
from typing import Any
from pathlib import Path

_log = logging.getLogger(__name__)


def dispatch_command(conn: Any, payload: dict) -> None:
    """Route command_type to the appropriate handler.

    Raises ValueError for unknown command types.
    """
    command_type = str(payload.get("command_type") or "").strip()
    if not command_type:
        raise ValueError("command_type required")

    handlers = {
        "upsert_worker": _apply_upsert_worker,
        "deactivate_worker": _apply_deactivate_worker,
        "create_project": _apply_create_project,
        "add_project_member": _apply_add_project_member,
        "assign_agent_to_project": _apply_assign_agent_to_project,
        "upsert_runtime_setting": _apply_upsert_runtime_setting,
        "upsert_kanban_card": _apply_upsert_kanban_card,
        "delete_kanban_card": _apply_delete_kanban_card,
        "create_knowledge_source": _apply_create_knowledge_source,
        "upsert_knowledge_document": _apply_upsert_knowledge_document,
        "upsert_knowledge_chunks": _apply_upsert_knowledge_chunks,
        "deactivate_knowledge_source": _apply_deactivate_knowledge_source,
        "upsert_prompt_policy": _apply_upsert_prompt_policy,
        "deactivate_prompt_policy": _apply_deactivate_prompt_policy,
    }
    handler = handlers.get(command_type)
    if handler is None:
        raise ValueError(f"Unknown command_type: {command_type}")

    handler(conn, payload)


def _resolve_worker_uid(conn: Any, worker_id: str, tenant_id: str) -> str | None:
    row = conn.execute(
        "SELECT worker_uid FROM main.admin_worker_catalog "
        "WHERE worker_id = ? AND tenant_id = ?",
        [worker_id, tenant_id],
    ).fetchone()
    return str(row[0]) if row else None


def _require_project_exists(conn: Any, project_id: str) -> str:
    """Raise ValueError if project does not exist or is not active. Returns tenant_id."""
    row = conn.execute(
        "SELECT tenant_id, active, status FROM main.admin_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Project not found: {project_id}")
    if not row[1] or str(row[2] or "").strip() == "archived":
        raise ValueError(f"Project is not active: {project_id}")
    return str(row[0])


def _require_worker_exists(conn: Any, worker_uid: str) -> str | None:
    """Raise ValueError if worker_uid does not exist or is not active. Returns tenant_id."""
    row = conn.execute(
        "SELECT tenant_id, active FROM main.admin_worker_catalog WHERE worker_uid = ?",
        [worker_uid],
    ).fetchone()
    if not row:
        raise ValueError(f"Worker not found: {worker_uid}")
    if not row[1]:
        raise ValueError(f"Worker is not active: {worker_uid}")
    return str(row[0])


def _apply_upsert_worker(conn: Any, payload: dict) -> None:
    worker_id = str(payload["worker_id"])
    display_name = str(payload.get("display_name", worker_id))
    tenant_id = str(payload.get("tenant_id", "default"))
    owner = str(payload.get("actor_email", "system"))
    source_kind = str(payload.get("source_kind", "runtime"))
    source_tpl = str(payload.get("source_template_id", "default"))
    visibility = str(payload.get("visibility", "private"))
    existing_uid = _resolve_worker_uid(conn, worker_id, tenant_id)

    if existing_uid:
        conn.execute(
            "UPDATE main.admin_worker_catalog "
            "SET display_name = ?, source_kind = ?, source_template_id = ?, "
            "visibility = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE worker_id = ? AND tenant_id = ?",
            [display_name, source_kind, source_tpl, visibility, worker_id, tenant_id],
        )
    else:
        wuid = str(payload.get("worker_uid", f"wrk_{uuid.uuid4().hex}"))
        conn.execute(
            "INSERT INTO main.admin_worker_catalog "
            "(worker_uid, tenant_id, owner_email, worker_id, display_name, "
            "source_kind, source_template_id, visibility, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, true)",
            [wuid, tenant_id, owner, worker_id, display_name, source_kind, source_tpl, visibility],
        )
        existing_uid = wuid

    # Version the snapshot if provided
    manifest = payload.get("manifest_snapshot")
    files = payload.get("files_snapshot")
    if manifest or files:
        import json as _json
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM main.admin_worker_versions "
            "WHERE worker_uid = ?", [existing_uid],
        ).fetchone()
        next_ver = (int(row[0]) if row[0] is not None else 0) + 1
        conn.execute(
            "INSERT INTO main.admin_worker_versions "
            "(worker_uid, version, manifest_snapshot_json, files_snapshot_json, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                existing_uid, next_ver,
                _json.dumps(manifest or {}, default=str, ensure_ascii=False),
                _json.dumps(files or {}, default=str, ensure_ascii=False),
                owner,
            ],
        )

    # Insert system_prompt as a context if provided
    system_prompt = str(payload.get("system_prompt", "")).strip()
    if system_prompt:
        import uuid as _uuid
        cid = f"ctx_{_uuid.uuid4().hex[:16]}"
        conn.execute(
            "INSERT OR REPLACE INTO main.admin_worker_contexts "
            "(context_id, worker_uid, title, content_md) VALUES (?, ?, 'system_prompt', ?)",
            [cid, existing_uid, system_prompt],
        )


def _apply_deactivate_worker(conn: Any, payload: dict) -> None:
    worker_id = str(payload["worker_id"])
    tenant_id = str(payload.get("tenant_id", "default"))
    conn.execute(
        "UPDATE main.admin_worker_catalog "
        "SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP "
        "WHERE worker_id = ? AND tenant_id = ?",
        [worker_id, tenant_id],
    )


def _apply_create_project(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    name = str(payload["name"])
    desc = str(payload.get("description", ""))
    tenant_id = str(payload.get("tenant_id", "default"))
    owner = str(payload.get("actor_email", "system"))

    existing = conn.execute(
        "SELECT project_id FROM main.admin_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_projects "
            "SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE project_id = ?",
            [name, desc, project_id],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_projects "
            "(project_id, tenant_id, owner_email, name, description, status, active) "
            "VALUES (?, ?, ?, ?, ?, 'active', true)",
            [project_id, tenant_id, owner, name, desc],
        )

    # Assign agents if provided
    agent_uids = payload.get("agent_worker_uids") or []
    if isinstance(agent_uids, list) and agent_uids:
        for wuid in agent_uids:
            if not isinstance(wuid, str) or not wuid.strip():
                continue
            wuid = str(wuid).strip()
            worker_tenant = _require_worker_exists(conn, wuid)
            if worker_tenant != tenant_id:
                raise ValueError(
                    f"Worker tenant mismatch: project={tenant_id} worker={worker_tenant}"
                )
            existing_agent = conn.execute(
                "SELECT worker_uid FROM main.admin_project_agents "
                "WHERE project_id = ? AND worker_uid = ?",
                [project_id, wuid],
            ).fetchone()
            if not existing_agent:
                conn.execute(
                    "INSERT INTO main.admin_project_agents "
                    "(project_id, worker_uid, role) VALUES (?, ?, 'member')",
                    [project_id, wuid],
                )


def _apply_upsert_runtime_setting(conn: Any, payload: dict) -> None:
    domain = str(payload["domain"])
    key = str(payload["key"])
    value = str(payload["value"])
    value_kind = str(payload.get("value_kind", "string"))
    secret = bool(payload.get("secret", False))
    tenant_id = str(payload.get("tenant_id", "default"))
    actor = str(payload.get("actor_email", "system"))

    existing = conn.execute(
        "SELECT setting_id FROM main.admin_runtime_settings "
        "WHERE tenant_id = ? AND actor_email = ? AND domain = ? AND key = ?",
        [tenant_id, actor, domain, key],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_runtime_settings "
            "SET value_text = ?, value_kind = ?, secret = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE setting_id = ?",
            [value, value_kind, secret, existing[0]],
        )
    else:
        setting_id = f"set_{uuid.uuid4().hex[:16]}"
        conn.execute(
            "INSERT INTO main.admin_runtime_settings "
            "(setting_id, tenant_id, actor_email, domain, key, value_text, value_kind, secret) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [setting_id, tenant_id, actor, domain, key, value, value_kind, secret],
        )


def _kanban_tags_json(raw: Any) -> str:
    tags = raw if isinstance(raw, list) else []
    clean = []
    for tag in tags:
        text = str(tag).strip()
        if text and text not in clean:
            clean.append(text[:64])
        if len(clean) >= 16:
            break
    return json.dumps(clean, ensure_ascii=False)


def _kanban_event(conn: Any, *, card_id: str, event_type: str, actor_email: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO main.admin_kanban_events "
        "(event_id, card_id, event_type, payload_json, actor_email) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            f"evt_{uuid.uuid4().hex[:16]}",
            card_id,
            event_type,
            json.dumps(payload, ensure_ascii=False, default=str),
            actor_email,
        ],
    )


def _apply_upsert_kanban_card(conn: Any, payload: dict) -> None:
    card_id = str(payload["card_id"]).strip()
    if not card_id:
        raise ValueError("card_id required")

    tenant_id = str(payload.get("tenant_id", "default") or "default").strip() or "default"
    actor_email = str(payload.get("actor_email", "system") or "system").strip() or "system"
    title = str(payload.get("title") or "").strip()[:120]
    if not title:
        raise ValueError("title required")
    description = str(payload.get("description") or "").strip()[:2000]
    status = str(payload.get("status") or "todo").strip()
    if status not in {"todo", "in_progress", "done", "cancelled"}:
        raise ValueError(f"Invalid kanban status: {status}")
    priority = int(payload.get("priority") or 0)
    sort_order = int(payload.get("sort_order") or 0)
    worker_id = str(payload.get("worker_id") or "").strip()[:128]
    tags_json = _kanban_tags_json(payload.get("tags"))

    existing = conn.execute(
        "SELECT tenant_id, actor_email FROM main.admin_kanban_cards WHERE card_id = ?",
        [card_id],
    ).fetchone()
    if existing and (str(existing[0]) != tenant_id or str(existing[1]) != actor_email):
        raise ValueError("Kanban card not found for tenant/actor")

    if existing:
        conn.execute(
            "UPDATE main.admin_kanban_cards "
            "SET title = ?, description = ?, status = ?, priority = ?, sort_order = ?, "
            "assignee_email = ?, tags_json = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE card_id = ?",
            [title, description, status, priority, sort_order, worker_id, tags_json, card_id],
        )
        event_type = "kanban_card.updated"
    else:
        conn.execute(
            "INSERT INTO main.admin_kanban_cards "
            "(card_id, tenant_id, actor_email, title, description, status, priority, sort_order, "
            "assignee_email, tags_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [card_id, tenant_id, actor_email, title, description, status, priority, sort_order, worker_id, tags_json],
        )
        event_type = "kanban_card.created"

    _kanban_event(
        conn,
        card_id=card_id,
        event_type=event_type,
        actor_email=actor_email,
        payload={"status": status, "title": title, "worker_id": worker_id},
    )


def _apply_delete_kanban_card(conn: Any, payload: dict) -> None:
    card_id = str(payload["card_id"]).strip()
    if not card_id:
        raise ValueError("card_id required")

    tenant_id = str(payload.get("tenant_id", "default") or "default").strip() or "default"
    actor_email = str(payload.get("actor_email", "system") or "system").strip() or "system"
    row = conn.execute(
        "SELECT title, status FROM main.admin_kanban_cards "
        "WHERE card_id = ? AND tenant_id = ? AND actor_email = ?",
        [card_id, tenant_id, actor_email],
    ).fetchone()
    if not row:
        raise ValueError("Kanban card not found")

    conn.execute("DELETE FROM main.admin_kanban_cards WHERE card_id = ?", [card_id])
    _kanban_event(
        conn,
        card_id=card_id,
        event_type="kanban_card.deleted",
        actor_email=actor_email,
        payload={"title": row[0], "status": row[1]},
    )


def _json_metadata(raw: Any) -> str:
    data = raw if isinstance(raw, dict) else {}
    return json.dumps(data, ensure_ascii=False, default=str)


_PROMPT_POLICY_ALIASES = {
    "capabilities": "capability",
    "directives": "directive",
    "manager_tasks": "manager_task",
    "system_prompts": "system_prompt",
}
_PROMPT_POLICY_TYPES = {"directive", "capability", "system_prompt", "manager_task", "tool_directive"}
_PROMPT_POLICY_STATUSES = {"draft", "active", "inactive", "archived"}


def _normalize_prompt_policy_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    normalized = _PROMPT_POLICY_ALIASES.get(value, value)
    if normalized not in _PROMPT_POLICY_TYPES:
        raise ValueError(f"Invalid prompt policy type: {raw}")
    return normalized


def _prompt_policy_id(policy_type: str, policy_name: str, version: int) -> str:
    digest = hashlib.sha256(f"{policy_type}:{policy_name}:{version}".encode("utf-8")).hexdigest()
    return f"ppol_{digest[:24]}"


def _apply_upsert_prompt_policy(conn: Any, payload: dict) -> None:
    policy_type = _normalize_prompt_policy_type(payload.get("policy_type"))
    policy_name = str(payload.get("policy_name") or "").strip()
    if not policy_name:
        raise ValueError("policy_name required")
    version = int(payload.get("version") or 1)
    if version < 1:
        raise ValueError("version must be >= 1")
    status = str(payload.get("status") or "active").strip().lower()
    if status not in _PROMPT_POLICY_STATUSES:
        raise ValueError(f"Invalid prompt policy status: {status}")
    content = str(payload.get("content") or "")
    if not content.strip():
        raise ValueError("content required")
    metadata_json = _json_metadata(payload.get("metadata"))
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    active = status == "active"

    existing = conn.execute(
        "SELECT policy_id FROM main.prompt_policy_registry "
        "WHERE policy_type = ? AND policy_name = ? AND version = ?",
        [policy_type, policy_name, version],
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.prompt_policy_registry "
            "SET status = ?, content = ?, checksum = ?, metadata_json = ?, "
            "active = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE policy_type = ? AND policy_name = ? AND version = ?",
            [status, content, checksum, metadata_json, active, policy_type, policy_name, version],
        )
    else:
        policy_id = str(payload.get("policy_id") or "").strip() or _prompt_policy_id(
            policy_type,
            policy_name,
            version,
        )
        conn.execute(
            "INSERT INTO main.prompt_policy_registry "
            "(policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active],
        )


def _apply_deactivate_prompt_policy(conn: Any, payload: dict) -> None:
    policy_type = _normalize_prompt_policy_type(payload.get("policy_type"))
    policy_name = str(payload.get("policy_name") or "").strip()
    if not policy_name:
        raise ValueError("policy_name required")
    raw_version = payload.get("version")
    params: list[Any] = [policy_type, policy_name]
    version_clause = ""
    if raw_version is not None:
        version = int(raw_version)
        if version < 1:
            raise ValueError("version must be >= 1")
        version_clause = " AND version = ?"
        params.append(version)
    row = conn.execute(
        "SELECT policy_id FROM main.prompt_policy_registry "
        "WHERE policy_type = ? AND policy_name = ?" + version_clause + " LIMIT 1",
        params,
    ).fetchone()
    if not row:
        raise ValueError(f"Prompt policy not found: {policy_type}/{policy_name}")
    conn.execute(
        "UPDATE main.prompt_policy_registry "
        "SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP "
        "WHERE policy_type = ? AND policy_name = ?" + version_clause,
        params,
    )


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


def _apply_add_project_member(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    member_email = str(payload["member_email"])
    role = str(payload.get("role", "member"))
    assigned_by = str(payload.get("actor_email", "system"))

    _require_project_exists(conn, project_id)

    existing = conn.execute(
        "SELECT email FROM main.admin_project_members "
        "WHERE project_id = ? AND email = ?",
        [project_id, member_email],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_project_members SET role = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE project_id = ? AND email = ?",
            [role, project_id, member_email],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_project_members "
            "(project_id, email, role, assigned_by) VALUES (?, ?, ?, ?)",
            [project_id, member_email, role, assigned_by],
        )


def _apply_assign_agent_to_project(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    worker_uid = str(payload["worker_uid"])
    role = str(payload.get("role", "member"))
    sort_order = int(payload.get("sort_order", 0))

    project_tenant = _require_project_exists(conn, project_id)
    worker_tenant = _require_worker_exists(conn, worker_uid)
    if worker_tenant != project_tenant:
        raise ValueError(
            f"Worker tenant mismatch: project={project_tenant} worker={worker_tenant}"
        )

    existing = conn.execute(
        "SELECT worker_uid FROM main.admin_project_agents "
        "WHERE project_id = ? AND worker_uid = ?",
        [project_id, worker_uid],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_project_agents SET role = ?, sort_order = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE project_id = ? AND worker_uid = ?",
            [role, sort_order, project_id, worker_uid],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_project_agents "
            "(project_id, worker_uid, role, sort_order) VALUES (?, ?, ?, ?)",
            [project_id, worker_uid, role, sort_order],
        )
