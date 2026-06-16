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
import re
import uuid
from typing import Any
from pathlib import Path

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id
from duckclaw.write_handlers.access import (
    _apply_delete_authorized_user,
    _apply_delete_shared_db_grant,
    _apply_upsert_authorized_user,
    _apply_upsert_shared_db_grant,
)
from duckclaw.write_handlers.runtime import (
    _apply_append_task_audit,
    _apply_delete_agent_config_entries,
    _apply_forget_chat_state,
    _apply_upsert_agent_config_entries,
    _apply_upsert_runtime_setting,
    _ensure_task_audit_log_table,
)

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


def _require_project_access(
    conn: Any,
    *,
    project_id: str,
    tenant_id: str,
    actor_email: str,
    require_owner: bool = False,
) -> str:
    """Validate project tenant and actor authorization. Returns project tenant_id."""
    actor = str(actor_email or "system").strip().lower() or "system"
    row = conn.execute(
        """
        SELECT p.tenant_id, p.owner_email, p.active, p.status, m.email
        FROM main.admin_projects p
        LEFT JOIN main.admin_project_members m
          ON m.project_id = p.project_id AND lower(m.email) = lower(?)
        WHERE p.project_id = ?
          AND p.tenant_id = ?
        LIMIT 1
        """,
        [actor, project_id, tenant_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Project not found: {project_id}")
    if not row[2] or str(row[3] or "").strip() == "archived":
        raise ValueError(f"Project is not active: {project_id}")
    is_owner = str(row[1] or "").strip().lower() == actor
    is_member = bool(row[4])
    if require_owner and not is_owner:
        raise ValueError(f"Project owner required: {project_id}")
    if not require_owner and not (is_owner or is_member):
        raise ValueError(f"Project access denied: {project_id}")
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


def _apply_create_project(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    name = str(payload["name"])
    desc = str(payload.get("description", ""))
    visibility = str(payload.get("visibility", "private"))
    tenant_id = str(payload.get("tenant_id") or _require_project_exists(conn, project_id))
    owner = str(payload.get("actor_email", "system"))

    existing = conn.execute(
        "SELECT project_id FROM main.admin_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_projects "
            "SET name = ?, description = ?, visibility = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE project_id = ?",
            [name, desc, visibility, project_id],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_projects "
            "(project_id, tenant_id, owner_email, name, description, visibility, status, active) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', true)",
            [project_id, tenant_id, owner, name, desc, visibility],
        )
        conn.execute(
            "INSERT INTO main.admin_project_members "
            "(project_id, email, role, assigned_by) VALUES (?, ?, 'owner', ?) "
            "ON CONFLICT (project_id, email) DO UPDATE SET "
            "role = EXCLUDED.role, assigned_by = EXCLUDED.assigned_by, updated_at = now()",
            [project_id, owner, owner],
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


def _managed_draft_actor_tenant(conn: Any, payload: dict) -> tuple[str, str]:
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    requested_tenant = str(payload.get("tenant_id") or "").strip()
    if "@" not in actor:
        return actor, requested_tenant or "default"
    profile = ensure_profile_for_user(conn, email=actor)
    tenant_id = str(profile.get("tenant_id") or "").strip()
    if requested_tenant and tenant_id and requested_tenant != tenant_id:
        raise ValueError(f"Tenant mismatch for actor: {actor}")
    return str(profile.get("email") or actor), tenant_id or requested_tenant or "default"


def _managed_draft_worker_id(raw: Any) -> str:
    worker_id = sanitize_catalog_worker_id(str(raw or "")).replace("_", "-").strip("-")
    if not worker_id:
        raise ValueError("worker_id required")
    return worker_id[:64]


def _managed_draft_available_skill_names(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not bool(item.get("available")):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name[:128])
    return names


def _managed_draft_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


def _managed_draft_snapshot_exists(
    conn: Any,
    *,
    worker_uid: str,
    manifest_snapshot: dict[str, Any],
    files_snapshot: dict[str, str],
    change_note: str,
) -> bool:
    expected_manifest = _managed_draft_json(manifest_snapshot)
    expected_files = _managed_draft_json(files_snapshot)
    rows = conn.execute(
        "SELECT manifest_snapshot_json, files_snapshot_json, change_note "
        "FROM main.admin_worker_versions WHERE worker_uid = ?",
        [worker_uid],
    ).fetchall()
    return any(
        _managed_draft_json(json.loads(str(row[0] or "{}"))) == expected_manifest
        and _managed_draft_json(json.loads(str(row[1] or "{}"))) == expected_files
        and str(row[2] or "") == change_note
        for row in rows
    )


def _ensure_managed_draft_project(conn: Any, payload: dict, *, actor: str, tenant_id: str) -> None:
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id required")
    existing = conn.execute("SELECT project_id FROM main.admin_projects WHERE project_id = ?", [project_id]).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.admin_projects "
            "SET name = ?, description = ?, visibility = 'private', active = true, "
            "status = 'active', updated_at = CURRENT_TIMESTAMP "
            "WHERE project_id = ? AND tenant_id = ?",
            [str(payload.get("project_name") or "Proyecto"), str(payload.get("project_description") or ""), project_id, tenant_id],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_projects "
            "(project_id, tenant_id, owner_email, name, description, visibility, status, active) "
            "VALUES (?, ?, ?, ?, ?, 'private', 'active', true)",
            [project_id, tenant_id, actor, str(payload.get("project_name") or "Proyecto"), str(payload.get("project_description") or "")],
        )
    conn.execute(
        "INSERT INTO main.admin_project_members (project_id, email, role, assigned_by) "
        "VALUES (?, ?, 'owner', ?) ON CONFLICT (project_id, email) DO UPDATE SET "
        "role = EXCLUDED.role, assigned_by = EXCLUDED.assigned_by, updated_at = now()",
        [project_id, actor, actor],
    )


def _upsert_managed_draft_worker(
    conn: Any,
    *,
    tenant_id: str,
    actor: str,
    worker_id: str,
    display_name: str,
    source_kind: str,
) -> str:
    existing_uid = _resolve_worker_uid(conn, worker_id, tenant_id)
    if existing_uid:
        conn.execute(
            "UPDATE main.admin_worker_catalog "
            "SET display_name = ?, source_kind = ?, source_template_id = 'default', "
            "visibility = 'private', status = 'active', active = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE worker_uid = ?",
            [display_name, source_kind, existing_uid],
        )
        return existing_uid
    worker_uid = f"wrk_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO main.admin_worker_catalog "
        "(worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, "
        "source_template_id, visibility, status, active) "
        "VALUES (?, ?, ?, ?, ?, ?, 'default', 'private', 'active', true)",
        [worker_uid, tenant_id, actor, worker_id, display_name, source_kind],
    )
    return worker_uid


def _ensure_managed_draft_version(
    conn: Any,
    *,
    worker_uid: str,
    actor: str,
    manifest_snapshot: dict[str, Any],
    files_snapshot: dict[str, str],
    change_note: str,
) -> None:
    if _managed_draft_snapshot_exists(
        conn,
        worker_uid=worker_uid,
        manifest_snapshot=manifest_snapshot,
        files_snapshot=files_snapshot,
        change_note=change_note,
    ):
        return
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM main.admin_worker_versions WHERE worker_uid = ?",
        [worker_uid],
    ).fetchone()
    next_version = int(row[0] or 1) if row else 1
    conn.execute(
        "INSERT INTO main.admin_worker_versions "
        "(worker_uid, version, manifest_snapshot_json, files_snapshot_json, created_by, change_note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [worker_uid, next_version, _managed_draft_json(manifest_snapshot), _managed_draft_json(files_snapshot), actor, change_note],
    )


def _ensure_managed_draft_context(
    conn: Any,
    *,
    worker_uid: str,
    title: str,
    content_md: str,
) -> None:
    if not content_md.strip():
        return
    existing = conn.execute(
        "SELECT context_id FROM main.admin_worker_contexts "
        "WHERE worker_uid = ? AND title = ? AND active = true LIMIT 1",
        [worker_uid, title],
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.admin_worker_contexts "
            "SET content_md = ?, sort_order = 0, updated_at = CURRENT_TIMESTAMP WHERE context_id = ?",
            [content_md, existing[0]],
        )
        return
    conn.execute(
        "INSERT INTO main.admin_worker_contexts (context_id, worker_uid, title, content_md, sort_order, active) "
        "VALUES (?, ?, ?, ?, 0, true)",
        [f"ctx_{uuid.uuid4().hex}", worker_uid, title, content_md],
    )


def _assign_managed_draft_agent(
    conn: Any,
    *,
    project_id: str,
    worker_uid: str,
    role: str,
    sort_order: int,
) -> None:
    conn.execute(
        "INSERT INTO main.admin_project_agents (project_id, worker_uid, role, sort_order, active) "
        "VALUES (?, ?, ?, ?, true) ON CONFLICT (project_id, worker_uid) DO UPDATE SET "
        "role = EXCLUDED.role, sort_order = EXCLUDED.sort_order, active = true, updated_at = now()",
        [project_id, worker_uid, role, sort_order],
    )


def _apply_confirm_workspace_managed_draft(conn: Any, payload: dict) -> None:
    actor, tenant_id = _managed_draft_actor_tenant(conn, payload)
    project_id = str(payload.get("project_id") or "").strip()
    source_kind = str(payload.get("source_kind") or "managed_draft").strip()[:64] or "managed_draft"
    change_note = str(payload.get("change_note") or "Created from DB-first managed draft").strip()[:256]
    context_title = str(payload.get("context_title") or "Contexto compartido").strip()[:160]
    shared_context = str(payload.get("shared_context") or "")
    skill_names = _managed_draft_available_skill_names(payload.get("suggested_skills"))
    _ensure_managed_draft_project(conn, payload, actor=actor, tenant_id=tenant_id)
    seen_workers: set[str] = set()
    for index, worker in enumerate(payload.get("workers") or []):
        if not isinstance(worker, dict):
            continue
        worker_id = _managed_draft_worker_id(worker.get("worker_id"))
        if worker_id in seen_workers:
            continue
        seen_workers.add(worker_id)
        display_name = str(worker.get("display_name") or worker_id).strip()[:128] or worker_id
        worker_uid = _upsert_managed_draft_worker(
            conn,
            tenant_id=tenant_id,
            actor=actor,
            worker_id=worker_id,
            display_name=display_name,
            source_kind=source_kind,
        )
        manifest_snapshot = {
            "id": worker_id,
            "name": display_name,
            "description": str(payload.get("project_description") or ""),
            "skills": skill_names,
        }
        files_snapshot = {
            "system_prompt.md": str(worker.get("system_prompt") or ""),
            "soul.md": shared_context,
        }
        _ensure_managed_draft_version(
            conn,
            worker_uid=worker_uid,
            actor=actor,
            manifest_snapshot=manifest_snapshot,
            files_snapshot=files_snapshot,
            change_note=change_note,
        )
        _ensure_managed_draft_context(
            conn,
            worker_uid=worker_uid,
            title=context_title,
            content_md=shared_context,
        )
        _assign_managed_draft_agent(
            conn,
            project_id=project_id,
            worker_uid=worker_uid,
            role=str(worker.get("role") or "member").strip()[:64] or "member",
            sort_order=index,
        )


def _apply_upsert_console_user(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import upsert_console_user

    upsert_console_user(
        conn,
        email=str(payload.get("email") or ""),
        nombre=str(payload.get("nombre") or ""),
        rol=str(payload.get("rol") or "user"),
        password=payload.get("password"),
        initials=str(payload.get("initials") or ""),
        active=bool(payload.get("active", True)),
    )


def _apply_deactivate_console_user(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import deactivate_console_user

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    ok = deactivate_console_user(conn, email=email)
    if not ok:
        raise ValueError(f"Console user not found: {email}")


def _apply_record_admin_login_failure(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import record_login_failure

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    record_login_failure(conn, email)


def _apply_clear_admin_login_failures(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import clear_login_failures

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    clear_login_failures(conn, email)


def _apply_update_console_user_password_hash(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import update_console_user_password_hash

    email = str(payload.get("email") or "").strip()
    password_hash = str(payload.get("password_hash") or "").strip()
    hash_algo = str(payload.get("hash_algo") or "argon2id").strip()
    hash_params = payload.get("hash_params")
    if not email:
        raise ValueError("email required")
    if not password_hash:
        raise ValueError("password_hash required")
    if not isinstance(hash_params, dict):
        hash_params = {}
    update_console_user_password_hash(
        conn,
        email=email,
        password_hash=password_hash,
        hash_algo=hash_algo,
        hash_params=hash_params,
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


def _quote_duckdb_ident(value: str) -> str:
    ident = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident):
        raise ValueError(f"Invalid DuckDB identifier: {value}")
    return '"' + ident.replace('"', '""') + '"'


def _dedupe_lowered(values: Any) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        value = str(raw or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _apply_drop_legacy_duckdb_objects(conn: Any, payload: dict) -> None:
    schemas = _dedupe_lowered(payload.get("schemas"))
    main_tables = _dedupe_lowered(payload.get("main_tables"))
    if not schemas and not main_tables:
        raise ValueError("No legacy DuckDB objects requested")

    existing_schemas = {
        str(row[0]).lower()
        for row in conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
    }
    existing_main_tables = {
        str(row[0]).lower()
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }

    for table in main_tables:
        if table in existing_main_tables:
            conn.execute(f"DROP TABLE main.{_quote_duckdb_ident(table)}")

    for schema in schemas:
        if schema in existing_schemas:
            conn.execute(f"DROP SCHEMA {_quote_duckdb_ident(schema)} CASCADE")


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
    tenant_id = str(payload.get("tenant_id") or _require_project_exists(conn, project_id))
    actor_email = str(payload.get("actor_email", "system"))

    project_tenant = _require_project_access(
        conn,
        project_id=project_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
    )
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
            "UPDATE main.admin_project_agents SET role = ?, sort_order = ?, active = true, "
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


def _apply_set_project_status(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    tenant_id = str(payload.get("tenant_id") or _require_project_exists(conn, project_id))
    actor_email = str(payload.get("actor_email", "system"))
    status = str(payload.get("status", "")).strip().lower()
    if status not in {"active", "inactive"}:
        raise ValueError(f"Invalid project status: {status}")
    _require_project_access(
        conn,
        project_id=project_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        require_owner=True,
    )
    conn.execute(
        "UPDATE main.admin_projects "
        "SET status = ?, active = true, updated_at = CURRENT_TIMESTAMP "
        "WHERE project_id = ? AND tenant_id = ?",
        [status, project_id, tenant_id],
    )


def _apply_delete_project(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    tenant_id = str(payload.get("tenant_id") or _require_project_exists(conn, project_id))
    actor_email = str(payload.get("actor_email", "system"))
    _require_project_access(
        conn,
        project_id=project_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        require_owner=True,
    )
    conn.execute(
        "DELETE FROM main.admin_project_agents WHERE project_id = ?",
        [project_id],
    )
    conn.execute(
        "DELETE FROM main.admin_project_members WHERE project_id = ?",
        [project_id],
    )
    conn.execute(
        "DELETE FROM main.admin_projects WHERE project_id = ? AND tenant_id = ?",
        [project_id, tenant_id],
    )


def _apply_detach_agent_from_project(conn: Any, payload: dict) -> None:
    project_id = str(payload["project_id"])
    worker_uid = str(payload["worker_uid"])
    tenant_id = str(payload.get("tenant_id") or _require_project_exists(conn, project_id))
    actor_email = str(payload.get("actor_email", "system"))
    project_tenant = _require_project_access(
        conn,
        project_id=project_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
    )
    worker_tenant = _require_worker_exists(conn, worker_uid)
    if worker_tenant != project_tenant:
        raise ValueError(
            f"Worker tenant mismatch: project={project_tenant} worker={worker_tenant}"
        )
    conn.execute(
        "UPDATE main.admin_project_agents "
        "SET active = false, updated_at = CURRENT_TIMESTAMP "
        "WHERE project_id = ? AND worker_uid = ?",
        [project_id, worker_uid],
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
