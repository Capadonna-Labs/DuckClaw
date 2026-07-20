"""Runtime agents owned by authenticated admin-console users.

Spec: docs/architecture/GATEWAY_PROCESS_BOUNDARIES.md
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_ADMIN_USER_AGENTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_user_agents (
    tenant_id VARCHAR NOT NULL,
    owner_email VARCHAR NOT NULL,
    worker_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    source_template_id VARCHAR DEFAULT 'default',
    manifest_path VARCHAR NOT NULL,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, worker_id)
);
"""


def ensure_admin_user_agents_table(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    db.execute(_ADMIN_USER_AGENTS_DDL)


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def runtime_agents_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_RUNTIME_AGENTS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / ".duckclaw" / "runtime" / "agents").resolve()


def sanitize_worker_id(worker_id: str) -> str:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        raise ValueError("worker_id requerido")
    return wid[:64]


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(row.get("tenant_id") or ""),
        "owner_email": str(row.get("owner_email") or ""),
        "worker_id": str(row.get("worker_id") or ""),
        "display_name": str(row.get("display_name") or ""),
        "source_template_id": str(row.get("source_template_id") or "default"),
        "manifest_path": str(row.get("manifest_path") or ""),
        "active": bool(row.get("active", True)),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _default_agent(profile: dict[str, Any]) -> dict[str, Any]:
    wid = str(profile.get("default_worker_id") or "default").strip() or "default"
    return {
        "tenant_id": str(profile.get("tenant_id") or ""),
        "owner_email": str(profile.get("email") or ""),
        "worker_id": wid,
        "display_name": "Agente default",
        "source_template_id": wid,
        "manifest_path": "",
        "active": True,
        "created_at": str(profile.get("created_at") or ""),
        "updated_at": str(profile.get("updated_at") or ""),
    }


def list_user_agents(db: Any, owner_email: str) -> list[dict[str, Any]]:
    ensure_admin_user_agents_table(db)
    profile = ensure_profile_for_user(db, email=owner_email)
    tenant_sql = _sql_lit(profile["tenant_id"], 128)
    rows = _query_all_dicts(
        db,
        "SELECT tenant_id, owner_email, worker_id, display_name, source_template_id, "
        "manifest_path, active, created_at, updated_at "
        f"FROM main.admin_user_agents WHERE tenant_id = '{tenant_sql}' AND active = true "
        "ORDER BY worker_id",
    )
    agents = [_row_to_public(r) for r in rows if isinstance(r, dict)]
    default = _default_agent(profile)
    if all(a["worker_id"] != default["worker_id"] for a in agents):
        return [default, *agents]
    return agents


def create_runtime_agent(
    db: Any,
    *,
    owner_email: str,
    worker_id: str,
    display_name: str,
    source_template_id: str = "default",
    system_prompt: str = "",
    description: str = "",
    skills: list[str] | None = None,
) -> dict[str, Any]:
    from duckclaw.admin_worker_catalog import (
        add_worker_context,
        add_worker_version,
        create_worker,
        get_worker_by_tenant_worker_id,
    )

    ensure_admin_user_agents_table(db)
    profile = ensure_profile_for_user(db, email=owner_email)
    wid = sanitize_worker_id(worker_id)
    tenant_id = profile["tenant_id"]
    if any(a["worker_id"] == wid for a in list_user_agents(db, owner_email)):
        raise ValueError(f"Agente ya existe: {wid}")
    if get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=wid):
        raise ValueError(f"Agente ya existe: {wid}")

    agent_dir = runtime_agents_root() / tenant_id / wid
    agent_dir.mkdir(parents=True, exist_ok=False)
    prompt = (system_prompt or "").strip()
    from duckclaw.framework_tool_pack import ensure_baseline_skills

    merged_skills = ensure_baseline_skills(
        list(skills or []),
        manifest={"tool_profile": "general"},
    )
    manifest = {
        "id": wid,
        "display_name": (display_name or wid).strip(),
        "owner_email": profile["email"],
        "tenant_id": tenant_id,
        "source_template_id": (source_template_id or "default").strip() or "default",
        "description": (description or "").strip(),
        "system_prompt": prompt,
        "skills": merged_skills,
        "tool_profile": "general",
    }
    manifest_path = agent_dir / "manifest.json"
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    manifest_path.write_text(manifest_json, encoding="utf-8")

    db.execute(
        f"""
        INSERT INTO main.admin_user_agents
          (tenant_id, owner_email, worker_id, display_name, source_template_id, manifest_path, active)
        VALUES (
          '{_sql_lit(tenant_id, 128)}',
          '{_sql_lit(profile["email"], 256)}',
          '{_sql_lit(wid, 64)}',
          '{_sql_lit((display_name or wid).strip(), 256)}',
          '{_sql_lit((source_template_id or "default").strip() or "default", 64)}',
          '{_sql_lit(str(manifest_path), 1024)}',
          true
        )
        """
    )
    worker = create_worker(
        db,
        owner_email=profile["email"],
        worker_id=wid,
        display_name=(display_name or wid).strip(),
        source_kind="runtime",
        source_template_id=(source_template_id or "default").strip() or "default",
        visibility="private",
    )
    files_snapshot = {"manifest.json": manifest_json}
    if prompt:
        files_snapshot["system_prompt.md"] = prompt
        add_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            title="system_prompt.md",
            content_md=prompt,
            sort_order=10,
        )
    add_worker_version(
        db,
        worker_uid=worker["worker_uid"],
        created_by=profile["email"],
        manifest_snapshot=manifest,
        files_snapshot=files_snapshot,
        change_note="Agente runtime creado desde consola admin",
    )
    return next(a for a in list_user_agents(db, owner_email) if a["worker_id"] == wid)
