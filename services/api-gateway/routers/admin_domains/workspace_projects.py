from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from core.admin_identity import (
    effective_actor_email,
    list_workspace_projects_page_for_actor,
    open_gateway_db,
    project_context_for_actor,
)
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import get_visible_worker_for_actor
from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.write_commands import (
    AssignAgentToProjectCommand,
    CreateProjectCommand,
    DeleteProjectCommand,
    DetachAgentFromProjectCommand,
    SetProjectStatusCommand,
)

router = APIRouter(tags=["admin-workspace-projects"])


class WorkspaceProjectBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    visibility: str = "private"


class ProjectAgentBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    role: str = "member"
    sort_order: int = 0


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _enqueue_workspace_project_command(command: Any) -> str:
    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        raise ValueError(command_status.detail or "workspace project write failed")
    return task_id


def _actor_profile(actor: str) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _project_snapshot(project_id: str, actor: str, *, include_inactive: bool = True) -> dict[str, Any] | None:
    with open_gateway_db(read_only=True) as db:
        if not include_inactive:
            return project_context_for_actor(db, actor_email=actor, project_id=project_id)
        page = list_workspace_projects_page_for_actor(
            db,
            actor_email=actor,
            status="all",
            limit=100,
            offset=0,
        )
    for project in list(page.get("projects") or []):
        if str(project.get("project_id") or "") == project_id:
            return dict(project)
    return None


def _visible_worker_snapshot(worker_id: str, actor: str) -> dict[str, str]:
    with open_gateway_db(read_only=True) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise _problem(404, "Worker no visible en catálogo", worker_id)
    return {
        "worker_uid": str(worker.get("worker_uid") or ""),
        "tenant_id": str(worker.get("tenant_id") or "default"),
        "worker_id": str(worker.get("worker_id") or worker_id),
        "display_name": str(worker.get("display_name") or worker_id),
    }


@router.get("/workspace/projects", dependencies=[Depends(require_admin_key)])
async def list_workspace_projects(
    q: str = "",
    status: str = "active",
    sort: str = "updated_at",
    direction: str = "desc",
    limit: int = 25,
    offset: int = 0,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    with open_gateway_db(read_only=True) as db:
        return list_workspace_projects_page_for_actor(
            db,
            actor_email=actor,
            q=q,
            status=status,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
        )


@router.post("/workspace/projects", dependencies=[Depends(require_admin_key)])
async def create_workspace_project(
    body: WorkspaceProjectBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    project_id = f"prj_{uuid.uuid4().hex}"
    command = CreateProjectCommand(
        project_id=project_id,
        tenant_id=str(profile.get("tenant_id") or "default"),
        actor_email=str(profile.get("email") or effective_actor_email(actor)),
        name=body.name,
        description=body.description,
        visibility=body.visibility,
    )
    try:
        task_id = _enqueue_workspace_project_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), project_id) from exc
    project = {
        "project_id": project_id,
        "tenant_id": command.tenant_id,
        "owner_email": command.actor_email,
        "name": body.name,
        "description": body.description,
        "status": "active",
        "visibility": body.visibility,
        "created_at": "",
        "updated_at": "",
        "agent_count": 0,
        "agents": [],
    }
    return {"ok": True, "task_id": task_id, "project": project}


@router.get("/workspace/projects/{project_id}", dependencies=[Depends(require_admin_key)])
async def get_workspace_project(
    project_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor, include_inactive=False)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    agents = list(project.get("agents") or [])
    return {"project": project, "agents": agents}


@router.delete("/workspace/projects/{project_id}", dependencies=[Depends(require_admin_key)])
async def delete_workspace_project(
    project_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    command = DeleteProjectCommand(
        project_id=project_id,
        tenant_id=str(project.get("tenant_id") or "default"),
        actor_email=effective_actor_email(actor),
    )
    try:
        task_id = _enqueue_workspace_project_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), project_id) from exc
    return {"ok": True, "hard_deleted": True, "project_id": project_id, "task_id": task_id}


@router.post("/workspace/projects/{project_id}/deactivate", dependencies=[Depends(require_admin_key)])
async def deactivate_workspace_project(
    project_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return _set_workspace_project_status(project_id, actor, status_value="inactive")


@router.post("/workspace/projects/{project_id}/reactivate", dependencies=[Depends(require_admin_key)])
async def reactivate_workspace_project(
    project_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return _set_workspace_project_status(project_id, actor, status_value="active")


def _set_workspace_project_status(project_id: str, actor: str, *, status_value: str) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    command = SetProjectStatusCommand(
        project_id=project_id,
        tenant_id=str(project.get("tenant_id") or "default"),
        actor_email=effective_actor_email(actor),
        status=status_value,
    )
    try:
        task_id = _enqueue_workspace_project_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), project_id) from exc
    updated = {**project, "status": status_value}
    return {"ok": True, "task_id": task_id, "project": updated}


@router.get("/workspace/projects/{project_id}/agents", dependencies=[Depends(require_admin_key)])
async def list_workspace_project_agents(
    project_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    return {"agents": list(project.get("agents") or [])}


@router.post("/workspace/projects/{project_id}/agents", dependencies=[Depends(require_admin_key)])
async def attach_workspace_project_agent(
    project_id: str,
    body: ProjectAgentBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    worker = _visible_worker_snapshot(body.worker_id, actor)
    command = AssignAgentToProjectCommand(
        project_id=project_id,
        tenant_id=str(project.get("tenant_id") or "default"),
        actor_email=effective_actor_email(actor),
        worker_uid=worker["worker_uid"],
        role=body.role,
        sort_order=body.sort_order,
    )
    try:
        task_id = _enqueue_workspace_project_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), body.worker_id) from exc
    agent = {
        "project_id": project_id,
        "worker_uid": worker["worker_uid"],
        "worker_id": worker["worker_id"],
        "display_name": worker["display_name"],
        "role": body.role,
        "sort_order": str(body.sort_order),
    }
    return {"ok": True, "task_id": task_id, "agent": agent}


@router.delete("/workspace/projects/{project_id}/agents/{worker_id}", dependencies=[Depends(require_admin_key)])
async def detach_workspace_project_agent(
    project_id: str,
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    project = _project_snapshot(project_id, actor)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    worker = _visible_worker_snapshot(worker_id, actor)
    command = DetachAgentFromProjectCommand(
        project_id=project_id,
        tenant_id=str(project.get("tenant_id") or "default"),
        actor_email=effective_actor_email(actor),
        worker_uid=worker["worker_uid"],
    )
    try:
        task_id = _enqueue_workspace_project_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), worker_id) from exc
    return {"ok": True, "task_id": task_id}
