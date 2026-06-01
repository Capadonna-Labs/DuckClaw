"""DB-first admin identity: profiles, catalog workers, workspace projects."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from duckclaw import DuckClaw
from duckclaw.admin_user_profiles import ensure_profile_for_user, get_profile_by_email
from duckclaw.admin_worker_catalog import (
    add_catalog_worker_context,
    deactivate_visible_worker_for_actor,
    deactivate_worker_context,
    get_latest_worker_version,
    get_visible_worker_for_actor,
    list_visible_workers_for_actor,
    list_worker_contexts,
    reorder_worker_contexts,
    update_catalog_worker_file,
)
from duckclaw.admin_workspace import (
    attach_agent_to_project,
    create_project,
    detach_agent_from_project,
    list_project_agents,
    list_projects_with_agents_for_actor,
)
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import db_root, list_vault_options_for_user


@contextmanager
def open_gateway_db(*, read_only: bool = False) -> Iterator[Any]:
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise FileNotFoundError("Gateway DuckDB no disponible")
    db = DuckClaw(gw, read_only=read_only, engine="python")
    try:
        yield db
    finally:
        db.close()


def vault_user_id_for_actor(actor_email: str) -> str:
    actor = (actor_email or "").strip().lower()
    admin_email = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "").strip().lower()
    owner_id = (os.environ.get("DUCKCLAW_OWNER_ID") or "").strip()
    if admin_email and actor == admin_email and owner_id:
        return owner_id
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        tg = (profile.get("telegram_user_id") or "").strip()
        if tg:
            return tg
    return owner_id or "default"


def resolve_actor_default_vault_path(actor_email: str) -> tuple[str, str]:
    uid = vault_user_id_for_actor(actor_email)
    private = db_root() / "private" / uid
    if private.is_dir():
        for candidate in sorted(private.glob("*.duckdb")):
            if candidate.is_file():
                return str(candidate.resolve()), uid
    gw = (get_gateway_db_path() or "").strip()
    if gw and os.path.isfile(gw):
        return gw, uid
    raise FileNotFoundError(f"Sin bóveda DuckDB para actor {actor_email!r}")


def validate_vault_path_for_actor(actor_email: str, vault_path: str) -> str:
    raw = (vault_path or "").strip()
    if not raw:
        return resolve_actor_default_vault_path(actor_email)[0]
    repo = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    abs_path = raw if os.path.isabs(raw) else str((Path(repo) if repo else Path.cwd()) / raw.lstrip("/"))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Vault no encontrado: {vault_path}")
    uid = vault_user_id_for_actor(actor_email)
    norm = abs_path.replace("\\", "/")
    if f"/private/{uid}/" in norm or norm.endswith(f"/private/{uid}"):
        return abs_path
    if "/shared/" in norm:
        return abs_path
    raise PermissionError(f"Vault fuera del namespace del actor: {vault_path}")


def console_user_public(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id") or f"user-{user.get('email')}",
        "email": user.get("email"),
        "nombre": user.get("nombre"),
        "rol": user.get("rol"),
        "initials": user.get("initials") or "",
        "profile": user.get("profile") or {},
    }


def is_catalog_managed_worker(worker: dict[str, Any] | None) -> bool:
    """True for rows in ``admin_worker_catalog`` (import/runtime), not filesystem-only templates."""
    return bool(worker and str(worker.get("worker_uid") or "").strip())


def attach_profile_to_console_user(db: Any, user: dict[str, Any]) -> dict[str, Any]:
    email = str(user.get("email") or "").strip()
    if not email:
        return user
    profile = ensure_profile_for_user(db, email=email)
    out = dict(user)
    out["profile"] = profile
    return out


def list_templates_payload(db: Any, *, actor_email: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in list_visible_workers_for_actor(db, actor_email=actor_email):
        wid = str(row.get("id") or row.get("worker_id") or "")
        items.append(
            {
                "id": wid,
                "name": str(row.get("display_name") or row.get("name") or wid),
                "source": str(row.get("source") or "catalog"),
                "read_only": str(row.get("source") or "") == "catalog",
            }
        )
    return items


def catalog_template_detail(db: Any, *, actor_email: str, worker_id: str) -> dict[str, Any] | None:
    worker = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=worker_id)
    if not worker:
        return None
    latest = get_latest_worker_version(db, worker_uid=worker["worker_uid"]) or {}
    files_snapshot = dict(latest.get("files_snapshot") or {})
    contexts = list_worker_contexts(db, worker_uid=worker["worker_uid"])
    contents = dict(files_snapshot)
    for ctx in contexts:
        title = str(ctx.get("title") or "").strip()
        if title and title not in contents:
            contents[title] = str(ctx.get("content_md") or "")
    files = [{"path": path} for path in sorted(contents.keys())]
    if "manifest.yaml" not in contents and latest.get("manifest_snapshot"):
        import yaml

        contents["manifest.yaml"] = yaml.safe_dump(
            latest.get("manifest_snapshot"),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        if not any(f["path"] == "manifest.yaml" for f in files):
            files.insert(0, {"path": "manifest.yaml"})
    return {
        "id": worker["worker_id"],
        "source": "catalog",
        "read_only": True,
        "files": files,
        "contents": contents,
        "contexts": contexts,
    }


def playground_workers_for_actor(db: Any, *, actor_email: str) -> list[dict[str, str]]:
    from duckclaw.admin_user_agents import list_user_agents

    seen: set[str] = set()
    workers: list[dict[str, str]] = []
    for row in list_visible_workers_for_actor(db, actor_email=actor_email):
        wid = str(row.get("id") or row.get("worker_id") or "").strip()
        if not wid or wid in seen:
            continue
        seen.add(wid)
        workers.append(
            {
                "id": wid,
                "label": str(row.get("display_name") or row.get("name") or wid),
            }
        )
    for agent in list_user_agents(db, actor_email):
        wid = str(agent.get("worker_id") or "").strip()
        if not wid or wid in seen:
            continue
        seen.add(wid)
        workers.append({"id": wid, "label": str(agent.get("display_name") or wid)})
    return workers


def worker_allowed_for_actor(db: Any, *, actor_email: str, worker_id: str) -> bool:
    wid = (worker_id or "").strip()
    if not wid:
        return False
    if get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=wid):
        return True
    from duckclaw.admin_user_agents import list_user_agents

    return any(a.get("worker_id") == wid for a in list_user_agents(db, actor_email))


def resolve_playground_worker_for_project(
    db: Any,
    *,
    actor_email: str,
    project_id: str,
    worker_id: str,
) -> tuple[str, str]:
    """Returns (effective_worker_id, project_id). Raises ValueError/PermissionError."""
    pid = (project_id or "").strip()
    wid = (worker_id or "").strip() or "default"
    if not pid:
        if not worker_allowed_for_actor(db, actor_email=actor_email, worker_id=wid):
            raise PermissionError(f"Worker no asignado al catálogo: {wid}")
        return wid, ""
    agents = list_project_agents(db, project_id=pid, actor_email=actor_email)
    if not agents:
        raise PermissionError(f"Proyecto no visible: {pid}")
    allowed_ids = {str(a.get("worker_id") or "") for a in agents}
    if wid == "default" and "default" not in allowed_ids:
        wid = str(agents[0].get("worker_id") or "default")
    if wid not in allowed_ids:
        raise PermissionError(f"Worker {wid!r} no pertenece al proyecto {pid}")
    return wid, pid


def attach_project_agent_by_worker_id(
    db: Any,
    *,
    actor_email: str,
    project_id: str,
    worker_id: str,
    role: str,
    sort_order: int,
) -> dict[str, Any]:
    worker = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=worker_id)
    if not worker:
        raise ValueError(f"worker no visible: {worker_id}")
    attach_agent_to_project(
        db,
        project_id=project_id,
        worker_uid=worker["worker_uid"],
        role=role,
        sort_order=sort_order,
    )
    agents = list_project_agents(db, project_id=project_id, actor_email=actor_email)
    match = next((a for a in agents if a.get("worker_id") == worker_id), None)
    return {"agent": match or {"worker_id": worker_id, "role": role}}


def detach_project_agent_by_worker_id(
    db: Any,
    *,
    actor_email: str,
    project_id: str,
    worker_id: str,
) -> bool:
    worker = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=worker_id)
    if not worker:
        return False
    return detach_agent_from_project(
        db,
        project_id=project_id,
        worker_uid=worker["worker_uid"],
        actor_email=actor_email,
    )
