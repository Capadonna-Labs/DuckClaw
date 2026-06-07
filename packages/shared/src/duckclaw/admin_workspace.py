"""DB-first admin workspace: projects and agent membership."""

from __future__ import annotations

import uuid
from typing import Any

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema, get_worker_by_uid
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_ADMIN_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_projects (
    project_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    owner_email VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    description TEXT,
    status VARCHAR DEFAULT 'active',
    visibility VARCHAR DEFAULT 'private',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_projects_owner
    ON main.admin_projects (tenant_id, owner_email, status);
"""

_ADMIN_PROJECT_MEMBERS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_project_members (
    project_id VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    role VARCHAR NOT NULL DEFAULT 'member',
    assigned_by VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, email)
);
CREATE INDEX IF NOT EXISTS idx_admin_project_members_email
    ON main.admin_project_members (email);
"""

_ADMIN_PROJECT_AGENTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_project_agents (
    project_id VARCHAR NOT NULL,
    worker_uid VARCHAR NOT NULL,
    role VARCHAR NOT NULL DEFAULT 'member',
    sort_order INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, worker_uid)
);
CREATE INDEX IF NOT EXISTS idx_admin_project_agents_worker
    ON main.admin_project_agents (worker_uid);
"""


def ensure_admin_workspace_schema(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    ensure_admin_worker_catalog_schema(db)
    for ddl in (_ADMIN_PROJECTS_DDL, _ADMIN_PROJECT_MEMBERS_DDL, _ADMIN_PROJECT_AGENTS_DDL):
        for stmt in ddl.strip().split(";"):
            sql = stmt.strip()
            if sql:
                db.execute(sql)


def _project_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "project_id": str(row.get("project_id") or ""),
        "tenant_id": str(row.get("tenant_id") or ""),
        "owner_email": str(row.get("owner_email") or ""),
        "name": str(row.get("name") or ""),
        "description": str(row.get("description") or ""),
        "status": str(row.get("status") or "active"),
        "visibility": str(row.get("visibility") or "private"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _actor_has_project_access(db: Any, *, project_id: str, actor_email: str) -> bool:
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    rows = _query_all_dicts(
        db,
        "SELECT p.project_id FROM main.admin_projects p "
        "LEFT JOIN main.admin_project_members m ON m.project_id = p.project_id "
        f"WHERE p.project_id = '{_sql_lit(project_id, 64)}' "
        f"AND (p.owner_email = '{_sql_lit(email, 256)}' OR m.email = '{_sql_lit(email, 256)}') "
        "LIMIT 1",
    )
    return bool(rows)


def create_project(
    db: Any,
    *,
    owner_email: str,
    name: str,
    description: str = "",
    visibility: str = "private",
) -> dict[str, str]:
    ensure_admin_workspace_schema(db)
    profile = ensure_profile_for_user(db, email=owner_email)
    project_id = f"prj_{uuid.uuid4().hex}"
    db.execute(
        f"""
        INSERT INTO main.admin_projects
          (project_id, tenant_id, owner_email, name, description, visibility)
        VALUES (
          '{_sql_lit(project_id, 64)}',
          '{_sql_lit(profile["tenant_id"], 128)}',
          '{_sql_lit(profile["email"], 256)}',
          '{_sql_lit((name or "Proyecto").strip(), 256)}',
          '{_sql_lit(description, 4096)}',
          '{_sql_lit(visibility, 32)}'
        )
        """
    )
    db.execute(
        f"""
        INSERT INTO main.admin_project_members (project_id, email, role, assigned_by)
        VALUES (
          '{_sql_lit(project_id, 64)}',
          '{_sql_lit(profile["email"], 256)}',
          'owner',
          '{_sql_lit(profile["email"], 256)}'
        )
        """
    )
    rows = _query_all_dicts(
        db,
        "SELECT project_id, tenant_id, owner_email, name, description, status, visibility, created_at, updated_at "
        f"FROM main.admin_projects WHERE project_id = '{_sql_lit(project_id, 64)}'",
    )
    if not rows or not isinstance(rows[0], dict):
        raise RuntimeError("project insert failed")
    return _project_row(dict(rows[0]))


def list_projects_for_actor(db: Any, *, actor_email: str) -> list[dict[str, str]]:
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    rows = _query_all_dicts(
        db,
        "SELECT DISTINCT p.project_id, p.tenant_id, p.owner_email, p.name, p.description, "
        "p.status, p.visibility, p.created_at, p.updated_at, "
        "COALESCE(a.agent_count, 0) AS agent_count "
        "FROM main.admin_projects p "
        "LEFT JOIN main.admin_project_members m ON m.project_id = p.project_id "
        "LEFT JOIN ("
        "  SELECT project_id, COUNT(*) AS agent_count "
        "  FROM main.admin_project_agents WHERE active = true GROUP BY project_id"
        ") a ON a.project_id = p.project_id "
        f"WHERE p.active = true AND LOWER(p.status) = 'active' AND (p.owner_email = '{_sql_lit(email, 256)}' "
        f"OR m.email = '{_sql_lit(email, 256)}') "
        "ORDER BY p.updated_at DESC, p.created_at DESC, p.name",
    )
    projects: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            project = _project_row(dict(row))
            project["agent_count"] = int(row.get("agent_count") or 0)
            projects.append(project)
    return projects


def list_projects_page_for_actor(
    db: Any,
    *,
    actor_email: str,
    q: str = "",
    status: str = "active",
    sort: str = "updated_at",
    direction: str = "desc",
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    query = (q or "").strip().lower()
    safe_status = (status or "active").strip().lower()
    safe_limit = max(1, min(int(limit or 25), 100))
    safe_offset = max(0, int(offset or 0))
    sort_map = {
        "updated_at": "p.updated_at",
        "created_at": "p.created_at",
        "name": "p.name",
        "agent_count": "agent_count",
    }
    sort_expr = sort_map.get((sort or "updated_at").strip().lower(), "p.updated_at")
    sort_dir = "ASC" if (direction or "").strip().lower() == "asc" else "DESC"
    where = [
        "p.active = true",
        f"(p.owner_email = '{_sql_lit(email, 256)}' OR m.email = '{_sql_lit(email, 256)}')",
    ]
    if safe_status and safe_status != "all":
        where.append(f"LOWER(p.status) = '{_sql_lit(safe_status, 32)}'")
    if query:
        like = _sql_lit(f"%{query}%", 512)
        where.append(
            "(LOWER(p.name) LIKE '"
            + like
            + "' OR LOWER(COALESCE(p.description, '')) LIKE '"
            + like
            + "' OR LOWER(p.project_id) LIKE '"
            + like
            + "')"
        )
    where_sql = " AND ".join(where)
    base_from = (
        "FROM main.admin_projects p "
        "LEFT JOIN main.admin_project_members m ON m.project_id = p.project_id "
        "LEFT JOIN ("
        "  SELECT project_id, COUNT(*) AS agent_count "
        "  FROM main.admin_project_agents WHERE active = true GROUP BY project_id"
        ") a ON a.project_id = p.project_id "
    )
    total_rows = _query_all_dicts(
        db,
        "SELECT COUNT(DISTINCT p.project_id) AS total " + base_from + f"WHERE {where_sql}",
    )
    rows = _query_all_dicts(
        db,
        "SELECT DISTINCT p.project_id, p.tenant_id, p.owner_email, p.name, p.description, "
        "p.status, p.visibility, p.created_at, p.updated_at, "
        "COALESCE(a.agent_count, 0) AS agent_count "
        + base_from
        + f"WHERE {where_sql} "
        + f"ORDER BY {sort_expr} {sort_dir}, p.created_at DESC, p.name "
        + f"LIMIT {safe_limit} OFFSET {safe_offset}",
    )
    projects: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            project = _project_row(dict(row))
            project["agent_count"] = int(row.get("agent_count") or 0)
            project["agents"] = list_project_agents(
                db,
                project_id=str(project.get("project_id") or ""),
                actor_email=email,
            )
            projects.append(project)
    total = int(total_rows[0].get("total") or 0) if total_rows and isinstance(total_rows[0], dict) else 0
    return {"projects": projects, "total": total, "limit": safe_limit, "offset": safe_offset}


def attach_agent_to_project(
    db: Any,
    *,
    project_id: str,
    worker_uid: str,
    role: str = "member",
    sort_order: int = 0,
) -> None:
    ensure_admin_workspace_schema(db)
    worker = get_worker_by_uid(db, worker_uid)
    if not worker:
        raise ValueError(f"worker no encontrado: {worker_uid}")
    rows = _query_all_dicts(
        db,
        f"SELECT project_id FROM main.admin_projects WHERE project_id = '{_sql_lit(project_id, 64)}' LIMIT 1",
    )
    if not rows:
        raise ValueError(f"project no encontrado: {project_id}")
    existing = _query_all_dicts(
        db,
        "SELECT worker_uid FROM main.admin_project_agents "
        f"WHERE project_id = '{_sql_lit(project_id, 64)}' "
        f"AND worker_uid = '{_sql_lit(worker_uid, 64)}'",
    )
    if existing:
        db.execute(
            f"""
            UPDATE main.admin_project_agents
            SET active = true,
                role = '{_sql_lit(role, 64)}',
                sort_order = {int(sort_order)},
                updated_at = CURRENT_TIMESTAMP
            WHERE project_id = '{_sql_lit(project_id, 64)}'
              AND worker_uid = '{_sql_lit(worker_uid, 64)}'
            """
        )
        return
    db.execute(
        f"""
        INSERT INTO main.admin_project_agents (project_id, worker_uid, role, sort_order)
        VALUES (
          '{_sql_lit(project_id, 64)}',
          '{_sql_lit(worker_uid, 64)}',
          '{_sql_lit(role, 64)}',
          {int(sort_order)}
        )
        """
    )


def list_project_agents(
    db: Any,
    *,
    project_id: str,
    actor_email: str,
) -> list[dict[str, str]]:
    ensure_admin_workspace_schema(db)
    if not _actor_has_project_access(db, project_id=project_id, actor_email=actor_email):
        return []
    rows = _query_all_dicts(
        db,
        "SELECT pa.project_id, pa.worker_uid, pa.role, pa.sort_order, wc.worker_id, wc.display_name "
        "FROM main.admin_project_agents pa "
        "JOIN main.admin_worker_catalog wc ON wc.worker_uid = pa.worker_uid "
        f"WHERE pa.project_id = '{_sql_lit(project_id, 64)}' AND pa.active = true "
        "ORDER BY pa.sort_order, wc.display_name",
    )
    out: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append({key: str(row.get(key) or "") for key in row.keys()})
    return out


def list_projects_with_agents_for_actor(db: Any, *, actor_email: str) -> list[dict[str, Any]]:
    projects = list_projects_for_actor(db, actor_email=actor_email)
    return [
        {
            **project,
            "agents": list_project_agents(
                db,
                project_id=str(project.get("project_id") or ""),
                actor_email=actor_email,
            ),
        }
        for project in projects
    ]


def get_project_context_for_actor(db: Any, *, project_id: str, actor_email: str) -> dict[str, Any] | None:
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    pid = (project_id or "").strip()
    rows = _query_all_dicts(
        db,
        "SELECT p.project_id, p.tenant_id, p.owner_email, p.name, p.description, p.status, p.visibility, "
        "p.created_at, p.updated_at "
        "FROM main.admin_projects p "
        "LEFT JOIN main.admin_project_members m ON m.project_id = p.project_id "
        f"WHERE p.project_id = '{_sql_lit(pid, 64)}' "
        "AND p.active = true "
        "AND LOWER(p.status) = 'active' "
        f"AND (p.owner_email = '{_sql_lit(email, 256)}' OR m.email = '{_sql_lit(email, 256)}') "
        "LIMIT 1",
    )
    if not rows or not isinstance(rows[0], dict):
        return None
    project = _project_row(dict(rows[0]))
    project["agents"] = list_project_agents(db, project_id=pid, actor_email=email)
    return project


def set_project_status_for_actor(
    db: Any,
    *,
    project_id: str,
    actor_email: str,
    status: str,
) -> dict[str, Any] | None:
    """Set a reversible project status for projects owned by actor."""
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    pid = (project_id or "").strip()
    safe_status = (status or "").strip().lower()
    if safe_status not in {"active", "inactive"}:
        raise ValueError(f"status inválido: {status}")
    rows = _query_all_dicts(
        db,
        "SELECT project_id FROM main.admin_projects "
        f"WHERE project_id = '{_sql_lit(pid, 64)}' "
        f"AND owner_email = '{_sql_lit(email, 256)}' "
        "AND active = true LIMIT 1",
    )
    if not rows:
        return None
    db.execute(
        f"""
        UPDATE main.admin_projects
        SET status = '{_sql_lit(safe_status, 32)}',
            updated_at = CURRENT_TIMESTAMP
        WHERE project_id = '{_sql_lit(pid, 64)}'
          AND owner_email = '{_sql_lit(email, 256)}'
          AND active = true
        """
    )
    updated = _query_all_dicts(
        db,
        "SELECT project_id, tenant_id, owner_email, name, description, status, visibility, created_at, updated_at "
        "FROM main.admin_projects "
        f"WHERE project_id = '{_sql_lit(pid, 64)}' "
        f"AND owner_email = '{_sql_lit(email, 256)}' "
        "AND active = true LIMIT 1",
    )
    if not updated or not isinstance(updated[0], dict):
        return None
    project = _project_row(dict(updated[0]))
    project["agent_count"] = len(list_project_agents(db, project_id=pid, actor_email=email))
    project["agents"] = list_project_agents(db, project_id=pid, actor_email=email)
    return project


def delete_project_for_actor(db: Any, *, project_id: str, actor_email: str) -> bool:
    """Hard-delete a project owned by actor and its project-only relations."""
    ensure_admin_workspace_schema(db)
    email = (actor_email or "").strip().lower()
    pid = (project_id or "").strip()
    rows = _query_all_dicts(
        db,
        "SELECT project_id FROM main.admin_projects "
        f"WHERE project_id = '{_sql_lit(pid, 64)}' "
        f"AND owner_email = '{_sql_lit(email, 256)}' "
        "AND active = true LIMIT 1",
    )
    if not rows:
        return False
    db.execute(
        f"""
        DELETE FROM main.admin_project_agents
        WHERE project_id = '{_sql_lit(pid, 64)}'
        """
    )
    db.execute(
        f"""
        DELETE FROM main.admin_project_members
        WHERE project_id = '{_sql_lit(pid, 64)}'
        """
    )
    db.execute(
        f"""
        DELETE FROM main.admin_projects
        WHERE project_id = '{_sql_lit(pid, 64)}'
          AND owner_email = '{_sql_lit(email, 256)}'
        """
    )
    remaining = _query_all_dicts(
        db,
        "SELECT project_id FROM main.admin_projects "
        f"WHERE project_id = '{_sql_lit(pid, 64)}' "
        "AND active = true LIMIT 1",
    )
    return not bool(remaining)


def deactivate_project_for_actor(db: Any, *, project_id: str, actor_email: str) -> bool:
    """Backward-compatible name: project deletion is now hard-delete."""
    return delete_project_for_actor(db, project_id=project_id, actor_email=actor_email)


def detach_agent_from_project(
    db: Any,
    *,
    project_id: str,
    worker_uid: str,
    actor_email: str,
) -> bool:
    ensure_admin_workspace_schema(db)
    if not _actor_has_project_access(db, project_id=project_id, actor_email=actor_email):
        return False
    db.execute(
        f"""
        UPDATE main.admin_project_agents
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE project_id = '{_sql_lit(project_id, 64)}'
          AND worker_uid = '{_sql_lit(worker_uid, 64)}'
          AND active = true
        """
    )
    remaining = _query_all_dicts(
        db,
        "SELECT worker_uid FROM main.admin_project_agents "
        f"WHERE project_id = '{_sql_lit(project_id, 64)}' "
        f"AND worker_uid = '{_sql_lit(worker_uid, 64)}' AND active = true LIMIT 1",
    )
    return not bool(remaining)
