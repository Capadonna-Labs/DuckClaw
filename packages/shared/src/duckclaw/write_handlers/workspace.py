"""Workspace project and managed-draft typed write handlers."""
from __future__ import annotations

import json
import uuid
from typing import Any

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id
from duckclaw.write_handlers.workers import _resolve_worker_uid


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

    agent_uids = payload.get("agent_worker_uids") or []
    if isinstance(agent_uids, list) and agent_uids:
        for wuid in agent_uids:
            if not isinstance(wuid, str) or not wuid.strip():
                continue
            wuid = str(wuid).strip()
            worker_tenant = _require_worker_exists(conn, wuid)
            if worker_tenant != tenant_id:
                raise ValueError(f"Worker tenant mismatch: project={tenant_id} worker={worker_tenant}")
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
            [
                str(payload.get("project_name") or "Proyecto"),
                str(payload.get("project_description") or ""),
                project_id,
                tenant_id,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_projects "
            "(project_id, tenant_id, owner_email, name, description, visibility, status, active) "
            "VALUES (?, ?, ?, ?, ?, 'private', 'active', true)",
            [
                project_id,
                tenant_id,
                actor,
                str(payload.get("project_name") or "Proyecto"),
                str(payload.get("project_description") or ""),
            ],
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
        [
            worker_uid,
            next_version,
            _managed_draft_json(manifest_snapshot),
            _managed_draft_json(files_snapshot),
            actor,
            change_note,
        ],
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
    sort_order = 0

    for package in payload.get("spawn_imports") or []:
        if not isinstance(package, dict):
            continue
        manifest = package.get("manifest")
        files = package.get("files")
        if not isinstance(manifest, dict) or not isinstance(files, dict):
            raise ValueError("spawn_imports entries require manifest and files objects")
        from duckclaw.spawn_package_import import import_spawn_package_to_catalog

        imported = import_spawn_package_to_catalog(
            conn,
            owner_email=actor,
            manifest=manifest,
            files={str(k): str(v) for k, v in files.items()},
            worker_id_override=(
                str(package.get("worker_id_override") or "").strip() or None
            ),
            force_read_only=True,
        )
        worker_id = str(imported.get("worker_id") or "").strip()
        worker_uid = str(imported.get("worker_uid") or "").strip()
        if not worker_id or not worker_uid:
            raise ValueError("spawn package import did not return worker identity")
        if worker_id in seen_workers:
            continue
        seen_workers.add(worker_id)
        if shared_context.strip():
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
            role=str(package.get("role") or "member").strip()[:64] or "member",
            sort_order=sort_order,
        )
        sort_order += 1

    for worker in payload.get("workers") or []:
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
            sort_order=sort_order,
        )
        sort_order += 1


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
        raise ValueError(f"Worker tenant mismatch: project={project_tenant} worker={worker_tenant}")

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
        raise ValueError(f"Worker tenant mismatch: project={project_tenant} worker={worker_tenant}")
    conn.execute(
        "UPDATE main.admin_project_agents "
        "SET active = false, updated_at = CURRENT_TIMESTAMP "
        "WHERE project_id = ? AND worker_uid = ?",
        [project_id, worker_uid],
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("create_project", _apply_create_project)
register_handler("add_project_member", _apply_add_project_member)
register_handler("assign_agent_to_project", _apply_assign_agent_to_project)
register_handler("set_project_status", _apply_set_project_status)
register_handler("delete_project", _apply_delete_project)
register_handler("detach_agent_from_project", _apply_detach_agent_from_project)
register_handler("confirm_workspace_managed_draft", _apply_confirm_workspace_managed_draft)
