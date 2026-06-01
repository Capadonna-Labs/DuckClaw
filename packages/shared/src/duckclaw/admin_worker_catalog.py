"""DB-first worker catalog, contexts, skills and capabilities.

The catalog stores current worker identity only. Imported manifests/files are
versioned separately so the model stays normalized and auditable.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_WORKER_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")

_ADMIN_WORKER_CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_catalog (
    worker_uid VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    owner_email VARCHAR NOT NULL,
    worker_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    source_kind VARCHAR DEFAULT 'runtime',
    source_template_id VARCHAR DEFAULT 'default',
    visibility VARCHAR DEFAULT 'private',
    status VARCHAR DEFAULT 'active',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, worker_id)
);
CREATE INDEX IF NOT EXISTS idx_admin_worker_catalog_owner
    ON main.admin_worker_catalog (tenant_id, owner_email, active);
CREATE INDEX IF NOT EXISTS idx_admin_worker_catalog_visibility
    ON main.admin_worker_catalog (visibility, active);
"""

_ADMIN_WORKER_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_versions (
    worker_uid VARCHAR NOT NULL,
    version INTEGER NOT NULL,
    manifest_snapshot_json TEXT,
    files_snapshot_json TEXT,
    created_by VARCHAR NOT NULL,
    change_note VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_uid, version)
);
"""

_ADMIN_WORKER_ASSIGNMENTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_assignments (
    worker_uid VARCHAR NOT NULL,
    target_email VARCHAR NOT NULL,
    target_tenant_id VARCHAR,
    permission VARCHAR NOT NULL DEFAULT 'use',
    assigned_by VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_uid, target_email, permission)
);
CREATE INDEX IF NOT EXISTS idx_admin_worker_assignments_target
    ON main.admin_worker_assignments (target_email, target_tenant_id);
"""

_ADMIN_WORKER_CONTEXTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_contexts (
    context_id VARCHAR PRIMARY KEY,
    worker_uid VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    content_md TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_worker_contexts_worker
    ON main.admin_worker_contexts (worker_uid, active, sort_order);
"""

_ADMIN_SKILLS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_skills (
    skill_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    description TEXT,
    skill_type VARCHAR NOT NULL,
    implementation_ref VARCHAR NOT NULL,
    owner_email VARCHAR,
    tenant_id VARCHAR DEFAULT 'global',
    visibility VARCHAR DEFAULT 'private',
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_ADMIN_WORKER_SKILLS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_skills (
    worker_uid VARCHAR NOT NULL,
    skill_id VARCHAR NOT NULL,
    enabled BOOLEAN DEFAULT true,
    config_json TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_uid, skill_id)
);
"""

_ADMIN_CAPABILITIES_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_capabilities (
    capability_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    kind VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    description TEXT,
    schema_json TEXT,
    risk_level VARCHAR DEFAULT 'low',
    requires_secret BOOLEAN DEFAULT false,
    requires_network BOOLEAN DEFAULT false,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_ADMIN_WORKER_CAPABILITIES_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_worker_capabilities (
    worker_uid VARCHAR NOT NULL,
    capability_id VARCHAR NOT NULL,
    permission VARCHAR NOT NULL DEFAULT 'use',
    config_json TEXT,
    policy_json TEXT,
    quota_json TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_uid, capability_id)
);
"""


def ensure_admin_worker_catalog_schema(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    for ddl in (
        _ADMIN_WORKER_CATALOG_DDL,
        _ADMIN_WORKER_VERSIONS_DDL,
        _ADMIN_WORKER_ASSIGNMENTS_DDL,
        _ADMIN_WORKER_CONTEXTS_DDL,
        _ADMIN_SKILLS_DDL,
        _ADMIN_WORKER_SKILLS_DDL,
        _ADMIN_CAPABILITIES_DDL,
        _ADMIN_WORKER_CAPABILITIES_DDL,
    ):
        for stmt in ddl.strip().split(";"):
            sql = stmt.strip()
            if sql:
                db.execute(sql)


def sanitize_catalog_worker_id(worker_id: str) -> str:
    wid = _WORKER_ID_RE.sub("-", (worker_id or "").strip()).strip("-_").lower()
    if not wid:
        raise ValueError("worker_id requerido")
    return wid[:64]


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _first_row(db: Any, sql: str) -> dict[str, Any] | None:
    rows = _query_all_dicts(db, sql)
    if rows and isinstance(rows[0], dict):
        return dict(rows[0])
    return None


def _worker_row_to_public(row: dict[str, Any]) -> dict[str, str]:
    return {
        "worker_uid": str(row.get("worker_uid") or ""),
        "tenant_id": str(row.get("tenant_id") or ""),
        "owner_email": str(row.get("owner_email") or ""),
        "worker_id": str(row.get("worker_id") or ""),
        "display_name": str(row.get("display_name") or ""),
        "source_kind": str(row.get("source_kind") or "runtime"),
        "source_template_id": str(row.get("source_template_id") or "default"),
        "visibility": str(row.get("visibility") or "private"),
        "status": str(row.get("status") or "active"),
        "active": str(bool(row.get("active", True))),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def get_worker_by_uid(db: Any, worker_uid: str) -> dict[str, str] | None:
    ensure_admin_worker_catalog_schema(db)
    row = _first_row(
        db,
        "SELECT worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, "
        "source_template_id, visibility, status, active, created_at, updated_at "
        f"FROM main.admin_worker_catalog WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' LIMIT 1",
    )
    return _worker_row_to_public(row) if row else None


def get_worker_by_tenant_worker_id(db: Any, *, tenant_id: str, worker_id: str) -> dict[str, str] | None:
    ensure_admin_worker_catalog_schema(db)
    row = _first_row(
        db,
        "SELECT worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, "
        "source_template_id, visibility, status, active, created_at, updated_at "
        "FROM main.admin_worker_catalog "
        f"WHERE tenant_id = '{_sql_lit(tenant_id, 128)}' "
        f"AND worker_id = '{_sql_lit(sanitize_catalog_worker_id(worker_id), 64)}' "
        "LIMIT 1",
    )
    return _worker_row_to_public(row) if row else None


def create_worker(
    db: Any,
    *,
    owner_email: str,
    worker_id: str,
    display_name: str,
    source_kind: str = "runtime",
    source_template_id: str = "default",
    visibility: str = "private",
) -> dict[str, str]:
    ensure_admin_worker_catalog_schema(db)
    profile = ensure_profile_for_user(db, email=owner_email)
    wid = sanitize_catalog_worker_id(worker_id)
    existing = _first_row(
        db,
        "SELECT worker_uid FROM main.admin_worker_catalog "
        f"WHERE tenant_id = '{_sql_lit(profile['tenant_id'], 128)}' "
        f"AND worker_id = '{_sql_lit(wid, 64)}' LIMIT 1",
    )
    if existing:
        raise ValueError(f"worker_id ya existe para el tenant: {wid}")

    worker_uid = f"wrk_{uuid.uuid4().hex}"
    db.execute(
        f"""
        INSERT INTO main.admin_worker_catalog
          (worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, source_template_id, visibility)
        VALUES (
          '{_sql_lit(worker_uid, 64)}',
          '{_sql_lit(profile["tenant_id"], 128)}',
          '{_sql_lit(profile["email"], 256)}',
          '{_sql_lit(wid, 64)}',
          '{_sql_lit((display_name or wid).strip(), 256)}',
          '{_sql_lit(source_kind, 32)}',
          '{_sql_lit((source_template_id or "default").strip() or "default", 64)}',
          '{_sql_lit(visibility, 32)}'
        )
        """
    )
    created = get_worker_by_uid(db, worker_uid)
    if not created:
        raise RuntimeError("worker insert failed")
    return created


def list_visible_workers_for_actor(db: Any, *, actor_email: str) -> list[dict[str, str]]:
    """Return the public default worker plus DB-catalog workers visible to actor."""
    ensure_admin_worker_catalog_schema(db)
    actor = (actor_email or "").strip().lower()
    workers: list[dict[str, str]] = [
        {
            "id": "default",
            "worker_id": "default",
            "name": "Default",
            "display_name": "Default",
            "source": "template",
            "visibility": "public",
        }
    ]
    if "@" not in actor:
        return workers

    profile = ensure_profile_for_user(db, email=actor)
    rows = _query_all_dicts(
        db,
        "SELECT DISTINCT wc.worker_uid, wc.tenant_id, wc.owner_email, wc.worker_id, wc.display_name, "
        "wc.source_kind, wc.source_template_id, wc.visibility, wc.status, wc.active, wc.created_at, wc.updated_at "
        "FROM main.admin_worker_catalog wc "
        "LEFT JOIN main.admin_worker_assignments wa ON wa.worker_uid = wc.worker_uid "
        "WHERE wc.active = true "
        f"AND wc.tenant_id = '{_sql_lit(profile['tenant_id'], 128)}' "
        f"AND (wc.owner_email = '{_sql_lit(profile['email'], 256)}' "
        "OR wc.visibility = 'public' "
        f"OR wa.target_email = '{_sql_lit(profile['email'], 256)}') "
        "ORDER BY wc.display_name, wc.worker_id",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        public = _worker_row_to_public(dict(row))
        workers.append(
            {
                "id": public["worker_id"],
                "worker_uid": public["worker_uid"],
                "worker_id": public["worker_id"],
                "name": public["display_name"],
                "display_name": public["display_name"],
                "source": "catalog",
                "visibility": public["visibility"],
                "source_template_id": public["source_template_id"],
            }
        )
    return workers


def deactivate_visible_worker_for_actor(db: Any, *, actor_email: str, worker_id: str) -> dict[str, str] | None:
    """Soft-delete a catalog worker visible to actor. Does not touch template folders."""
    ensure_admin_worker_catalog_schema(db)
    actor = (actor_email or "").strip().lower()
    if "@" not in actor:
        return None
    profile = ensure_profile_for_user(db, email=actor)
    wid = sanitize_catalog_worker_id(worker_id)
    worker = get_worker_by_tenant_worker_id(db, tenant_id=profile["tenant_id"], worker_id=wid)
    if not worker or worker["owner_email"] != profile["email"]:
        return None
    db.execute(
        f"""
        UPDATE main.admin_worker_catalog
        SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE worker_uid = '{_sql_lit(worker["worker_uid"], 64)}'
        """
    )
    return worker


def add_worker_version(
    db: Any,
    *,
    worker_uid: str,
    created_by: str,
    manifest_snapshot: dict[str, Any] | None = None,
    files_snapshot: dict[str, Any] | None = None,
    change_note: str = "",
) -> dict[str, str | int]:
    ensure_admin_worker_catalog_schema(db)
    row = _first_row(
        db,
        "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
        f"FROM main.admin_worker_versions WHERE worker_uid = '{_sql_lit(worker_uid, 64)}'",
    )
    version = int(row.get("next_version") or 1) if row else 1
    db.execute(
        f"""
        INSERT INTO main.admin_worker_versions
          (worker_uid, version, manifest_snapshot_json, files_snapshot_json, created_by, change_note)
        VALUES (
          '{_sql_lit(worker_uid, 64)}',
          {version},
          '{_sql_lit(_json(manifest_snapshot), 65535)}',
          '{_sql_lit(_json(files_snapshot), 65535)}',
          '{_sql_lit(created_by, 256)}',
          '{_sql_lit(change_note, 512)}'
        )
        """
    )
    return {"worker_uid": worker_uid, "version": version}


def add_worker_context(
    db: Any,
    *,
    worker_uid: str,
    title: str,
    content_md: str,
    sort_order: int = 0,
) -> dict[str, str]:
    ensure_admin_worker_catalog_schema(db)
    context_id = f"ctx_{uuid.uuid4().hex}"
    db.execute(
        f"""
        INSERT INTO main.admin_worker_contexts
          (context_id, worker_uid, title, content_md, sort_order)
        VALUES (
          '{_sql_lit(context_id, 64)}',
          '{_sql_lit(worker_uid, 64)}',
          '{_sql_lit(title, 256)}',
          '{_sql_lit(content_md, 65535)}',
          {int(sort_order)}
        )
        """
    )
    return {"context_id": context_id, "worker_uid": worker_uid, "title": title}


def list_worker_contexts(db: Any, *, worker_uid: str) -> list[dict[str, str]]:
    ensure_admin_worker_catalog_schema(db)
    rows = _query_all_dicts(
        db,
        "SELECT context_id, worker_uid, title, content_md, sort_order, created_at, updated_at "
        f"FROM main.admin_worker_contexts WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        "AND active = true ORDER BY sort_order, created_at, context_id",
    )
    return [
        {
            "context_id": str(row.get("context_id") or ""),
            "worker_uid": str(row.get("worker_uid") or ""),
            "title": str(row.get("title") or ""),
            "content_md": str(row.get("content_md") or ""),
            "sort_order": str(row.get("sort_order") or "0"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def get_latest_worker_version(db: Any, *, worker_uid: str) -> dict[str, Any] | None:
    ensure_admin_worker_catalog_schema(db)
    row = _first_row(
        db,
        "SELECT worker_uid, version, manifest_snapshot_json, files_snapshot_json, created_by, "
        "change_note, created_at "
        "FROM main.admin_worker_versions "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        "ORDER BY version DESC LIMIT 1",
    )
    if not row:
        return None
    out = dict(row)
    for key in ("manifest_snapshot_json", "files_snapshot_json"):
        raw = str(out.get(key) or "{}")
        try:
            out[key.replace("_json", "")] = json.loads(raw)
        except json.JSONDecodeError:
            out[key.replace("_json", "")] = {}
    return out


def get_visible_worker_for_actor(db: Any, *, actor_email: str, worker_id: str) -> dict[str, str] | None:
    ensure_admin_worker_catalog_schema(db)
    actor = (actor_email or "").strip().lower()
    if "@" not in actor:
        return None
    profile = ensure_profile_for_user(db, email=actor)
    wid = sanitize_catalog_worker_id(worker_id)
    worker = get_worker_by_tenant_worker_id(db, tenant_id=profile["tenant_id"], worker_id=wid)
    if worker and worker["active"] == "True" and worker["owner_email"] == profile["email"]:
        return worker
    return None


def _update_context_content(db: Any, *, worker_uid: str, title: str, content_md: str) -> bool:
    rows = _query_all_dicts(
        db,
        "SELECT context_id FROM main.admin_worker_contexts "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        f"AND title = '{_sql_lit(title, 256)}' AND active = true LIMIT 1",
    )
    if not rows:
        return False
    context_id = str(rows[0].get("context_id") or "")
    if not context_id:
        return False
    db.execute(
        f"""
        UPDATE main.admin_worker_contexts
        SET content_md = '{_sql_lit(content_md, 65535)}',
            updated_at = CURRENT_TIMESTAMP
        WHERE context_id = '{_sql_lit(context_id, 64)}'
        """
    )
    return True


def update_catalog_worker_file(
    db: Any,
    *,
    worker_uid: str,
    file_path: str,
    content: str,
    actor_email: str,
) -> dict[str, Any]:
    """Update a DB-backed worker file snapshot, syncing markdown contexts when applicable."""
    ensure_admin_worker_catalog_schema(db)
    rel = (file_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("file_path inválido")
    latest = get_latest_worker_version(db, worker_uid=worker_uid)
    manifest_snapshot = dict((latest or {}).get("manifest_snapshot") or {})
    files_snapshot = dict((latest or {}).get("files_snapshot") or {})
    files_snapshot[rel] = content

    context_synced = False
    if rel.lower().endswith(".md"):
        context_synced = _update_context_content(
            db,
            worker_uid=worker_uid,
            title=rel,
            content_md=content,
        )
        if not context_synced:
            add_worker_context(db, worker_uid=worker_uid, title=rel, content_md=content, sort_order=100)
            context_synced = True

    version = add_worker_version(
        db,
        worker_uid=worker_uid,
        created_by=actor_email,
        manifest_snapshot=manifest_snapshot,
        files_snapshot=files_snapshot,
        change_note=f"Actualización DB-first de {rel}",
    )
    return {
        "worker_uid": worker_uid,
        "path": rel,
        "version": version["version"],
        "context_synced": context_synced,
    }


def add_catalog_worker_context(
    db: Any,
    *,
    worker_uid: str,
    title: str,
    content_md: str,
    sort_order: int,
    actor_email: str,
) -> dict[str, Any]:
    clean_title = (title or "").strip().replace("\\", "/").lstrip("/")
    if not clean_title or ".." in clean_title.split("/") or not clean_title.lower().endswith(".md"):
        raise ValueError("title debe ser un archivo .md válido")
    context = add_worker_context(
        db,
        worker_uid=worker_uid,
        title=clean_title,
        content_md=content_md,
        sort_order=sort_order,
    )
    latest = get_latest_worker_version(db, worker_uid=worker_uid)
    manifest_snapshot = dict((latest or {}).get("manifest_snapshot") or {})
    files_snapshot = dict((latest or {}).get("files_snapshot") or {})
    files_snapshot[clean_title] = content_md
    version = add_worker_version(
        db,
        worker_uid=worker_uid,
        created_by=actor_email,
        manifest_snapshot=manifest_snapshot,
        files_snapshot=files_snapshot,
        change_note=f"Nuevo contexto DB-first {clean_title}",
    )
    return {"context": context, "version": version["version"]}


def reorder_worker_contexts(db: Any, *, worker_uid: str, items: list[dict[str, Any]]) -> int:
    ensure_admin_worker_catalog_schema(db)
    updated = 0
    for item in items:
        context_id = str(item.get("context_id") or "").strip()
        if not context_id:
            continue
        sort_order = int(item.get("sort_order") or 0)
        db.execute(
            f"""
            UPDATE main.admin_worker_contexts
            SET sort_order = {sort_order}, updated_at = CURRENT_TIMESTAMP
            WHERE worker_uid = '{_sql_lit(worker_uid, 64)}'
              AND context_id = '{_sql_lit(context_id, 64)}'
              AND active = true
            """
        )
        updated += 1
    return updated


def deactivate_worker_context(
    db: Any,
    *,
    worker_uid: str,
    context_id: str,
    actor_email: str,
) -> dict[str, Any] | None:
    ensure_admin_worker_catalog_schema(db)
    row = _first_row(
        db,
        "SELECT context_id, title FROM main.admin_worker_contexts "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        f"AND context_id = '{_sql_lit(context_id, 64)}' AND active = true LIMIT 1",
    )
    if not row:
        return None
    title = str(row.get("title") or "")
    db.execute(
        f"""
        UPDATE main.admin_worker_contexts
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE worker_uid = '{_sql_lit(worker_uid, 64)}'
          AND context_id = '{_sql_lit(context_id, 64)}'
        """
    )
    latest = get_latest_worker_version(db, worker_uid=worker_uid)
    manifest_snapshot = dict((latest or {}).get("manifest_snapshot") or {})
    files_snapshot = dict((latest or {}).get("files_snapshot") or {})
    files_snapshot.pop(title, None)
    version = add_worker_version(
        db,
        worker_uid=worker_uid,
        created_by=actor_email,
        manifest_snapshot=manifest_snapshot,
        files_snapshot=files_snapshot,
        change_note=f"Contexto desactivado {title}",
    )
    return {"context_id": context_id, "title": title, "version": version["version"]}


def register_skill(
    db: Any,
    *,
    name: str,
    skill_type: str,
    implementation_ref: str,
    description: str = "",
    owner_email: str = "",
    tenant_id: str = "global",
    visibility: str = "private",
) -> dict[str, str]:
    ensure_admin_worker_catalog_schema(db)
    skill_name = (name or "").strip()
    existing = _first_row(
        db,
        f"SELECT skill_id, name, skill_type, implementation_ref FROM main.admin_skills "
        f"WHERE name = '{_sql_lit(skill_name, 128)}' LIMIT 1",
    )
    if existing:
        return {key: str(existing.get(key) or "") for key in ("skill_id", "name", "skill_type", "implementation_ref")}
    skill_id = f"skl_{uuid.uuid4().hex}"
    db.execute(
        f"""
        INSERT INTO main.admin_skills
          (skill_id, name, description, skill_type, implementation_ref, owner_email, tenant_id, visibility)
        VALUES (
          '{_sql_lit(skill_id, 64)}',
          '{_sql_lit(skill_name, 128)}',
          '{_sql_lit(description, 1024)}',
          '{_sql_lit(skill_type, 64)}',
          '{_sql_lit(implementation_ref, 512)}',
          '{_sql_lit(owner_email, 256)}',
          '{_sql_lit(tenant_id, 128)}',
          '{_sql_lit(visibility, 32)}'
        )
        """
    )
    return {"skill_id": skill_id, "name": skill_name, "skill_type": skill_type, "implementation_ref": implementation_ref}


def attach_skill_to_worker(
    db: Any,
    *,
    worker_uid: str,
    skill_id: str,
    config: dict[str, Any] | None = None,
    sort_order: int = 0,
) -> None:
    ensure_admin_worker_catalog_schema(db)
    existing = _first_row(
        db,
        "SELECT skill_id FROM main.admin_worker_skills "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' AND skill_id = '{_sql_lit(skill_id, 64)}'",
    )
    if existing:
        return
    db.execute(
        f"""
        INSERT INTO main.admin_worker_skills (worker_uid, skill_id, config_json, sort_order)
        VALUES (
          '{_sql_lit(worker_uid, 64)}',
          '{_sql_lit(skill_id, 64)}',
          '{_sql_lit(_json(config), 8192)}',
          {int(sort_order)}
        )
        """
    )


def list_worker_skills(db: Any, *, worker_uid: str) -> list[dict[str, str]]:
    ensure_admin_worker_catalog_schema(db)
    rows = _query_all_dicts(
        db,
        "SELECT s.skill_id, s.name, s.skill_type, s.implementation_ref "
        "FROM main.admin_worker_skills ws "
        "JOIN main.admin_skills s ON s.skill_id = ws.skill_id "
        f"WHERE ws.worker_uid = '{_sql_lit(worker_uid, 64)}' AND ws.enabled = true AND s.active = true "
        "ORDER BY ws.sort_order, s.name",
    )
    return [{key: str(row.get(key) or "") for key in ("skill_id", "name", "skill_type", "implementation_ref")} for row in rows]


def register_capability(
    db: Any,
    *,
    name: str,
    kind: str,
    provider: str,
    risk_level: str = "low",
    requires_secret: bool = False,
    requires_network: bool = False,
    description: str = "",
    schema: dict[str, Any] | None = None,
) -> dict[str, str]:
    ensure_admin_worker_catalog_schema(db)
    cap_name = (name or "").strip()
    existing = _first_row(
        db,
        "SELECT capability_id, name, kind, provider FROM main.admin_capabilities "
        f"WHERE name = '{_sql_lit(cap_name, 128)}' LIMIT 1",
    )
    if existing:
        return {key: str(existing.get(key) or "") for key in ("capability_id", "name", "kind", "provider")}
    capability_id = f"cap_{uuid.uuid4().hex}"
    db.execute(
        f"""
        INSERT INTO main.admin_capabilities
          (capability_id, name, kind, provider, description, schema_json, risk_level, requires_secret, requires_network)
        VALUES (
          '{_sql_lit(capability_id, 64)}',
          '{_sql_lit(cap_name, 128)}',
          '{_sql_lit(kind, 64)}',
          '{_sql_lit(provider, 128)}',
          '{_sql_lit(description, 1024)}',
          '{_sql_lit(_json(schema), 8192)}',
          '{_sql_lit(risk_level, 32)}',
          {str(bool(requires_secret)).lower()},
          {str(bool(requires_network)).lower()}
        )
        """
    )
    return {"capability_id": capability_id, "name": cap_name, "kind": kind, "provider": provider}


def grant_worker_capability(
    db: Any,
    *,
    worker_uid: str,
    capability_id: str,
    permission: str = "use",
    config: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> None:
    ensure_admin_worker_catalog_schema(db)
    existing = _first_row(
        db,
        "SELECT capability_id FROM main.admin_worker_capabilities "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        f"AND capability_id = '{_sql_lit(capability_id, 64)}'",
    )
    if existing:
        return
    db.execute(
        f"""
        INSERT INTO main.admin_worker_capabilities
          (worker_uid, capability_id, permission, config_json, policy_json)
        VALUES (
          '{_sql_lit(worker_uid, 64)}',
          '{_sql_lit(capability_id, 64)}',
          '{_sql_lit(permission, 32)}',
          '{_sql_lit(_json(config), 8192)}',
          '{_sql_lit(_json(policy), 8192)}'
        )
        """
    )


def list_worker_capabilities(db: Any, *, worker_uid: str) -> list[dict[str, str]]:
    ensure_admin_worker_catalog_schema(db)
    rows = _query_all_dicts(
        db,
        "SELECT c.capability_id, c.name, c.kind, c.provider, wc.permission "
        "FROM main.admin_worker_capabilities wc "
        "JOIN main.admin_capabilities c ON c.capability_id = wc.capability_id "
        f"WHERE wc.worker_uid = '{_sql_lit(worker_uid, 64)}' AND wc.enabled = true AND c.active = true "
        "ORDER BY c.name",
    )
    return [
        {key: str(row.get(key) or "") for key in ("capability_id", "name", "kind", "provider", "permission")}
        for row in rows
        if isinstance(row, dict)
    ]
