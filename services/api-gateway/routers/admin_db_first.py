"""DB-first admin routes (catalog import, workspace, user agents)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.admin import _actor_from_header, _problem, _require_admin_key

router = APIRouter(tags=["admin-db-first"])


class TemplateImportBody(BaseModel):
    templates_root: str = Field(..., min_length=1)
    include_prefixes: list[str] = Field(default_factory=list)
    include_template_ids: list[str] = Field(default_factory=list)


class TemplateContextBody(BaseModel):
    title: str = Field(..., min_length=1)
    content_md: str = ""
    sort_order: int = 0


class ContextReorderBody(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceProjectBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    visibility: str = "private"


class ProjectAgentBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    role: str = "member"
    sort_order: int = 0


class UserAgentCreateBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    source_template_id: str = "default"
    system_prompt: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


@router.post("/templates/import", dependencies=[Depends(_require_admin_key)])
async def import_templates_to_catalog(
    body: TemplateImportBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_template_import import import_templates_to_catalog as _import

    with open_gateway_db(read_only=False) as db:
        return _import(
            db,
            owner_email=actor,
            templates_root=body.templates_root,
            include_prefixes=tuple(body.include_prefixes),
            include_template_ids=tuple(body.include_template_ids),
        )


@router.post("/templates/{worker_id}/contexts", dependencies=[Depends(_require_admin_key)])
async def create_template_context(
    worker_id: str,
    body: TemplateContextBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import add_catalog_worker_context, get_visible_worker_for_actor

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        return add_catalog_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            title=body.title,
            content_md=body.content_md,
            sort_order=body.sort_order,
            actor_email=actor,
        )


@router.patch("/templates/{worker_id}/contexts/reorder", dependencies=[Depends(_require_admin_key)])
async def reorder_template_contexts(
    worker_id: str,
    body: ContextReorderBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import get_visible_worker_for_actor, reorder_worker_contexts

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        updated = reorder_worker_contexts(db, worker_uid=worker["worker_uid"], items=body.items)
    return {"updated": updated}


@router.delete("/templates/{worker_id}/contexts/{context_id}", dependencies=[Depends(_require_admin_key)])
async def delete_template_context(
    worker_id: str,
    context_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import deactivate_worker_context, get_visible_worker_for_actor

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        result = deactivate_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            context_id=context_id,
            actor_email=actor,
        )
        if not result:
            raise _problem(404, "Contexto no encontrado", context_id)
    return {"ok": True, **result}


@router.get("/workspace/projects", dependencies=[Depends(_require_admin_key)])
async def list_workspace_projects(actor: str = Depends(_actor_from_header)) -> dict[str, Any]:
    from core.admin_identity import list_projects_with_agents_for_actor, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        projects = list_projects_with_agents_for_actor(db, actor_email=actor)
    return {"projects": projects}


@router.post("/workspace/projects", dependencies=[Depends(_require_admin_key)])
async def create_workspace_project(
    body: WorkspaceProjectBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import create_project, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        project = create_project(
            db,
            owner_email=actor,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
        )
    return {"project": project}


@router.get("/workspace/projects/{project_id}/agents", dependencies=[Depends(_require_admin_key)])
async def list_workspace_project_agents(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import list_project_agents, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        agents = list_project_agents(db, project_id=project_id, actor_email=actor)
    return {"agents": agents}


@router.post("/workspace/projects/{project_id}/agents", dependencies=[Depends(_require_admin_key)])
async def attach_workspace_project_agent(
    project_id: str,
    body: ProjectAgentBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import attach_project_agent_by_worker_id, open_gateway_db

    try:
        with open_gateway_db(read_only=False) as db:
            return attach_project_agent_by_worker_id(
                db,
                actor_email=actor,
                project_id=project_id,
                worker_id=body.worker_id,
                role=body.role,
                sort_order=body.sort_order,
            )
    except ValueError as exc:
        raise _problem(400, str(exc), body.worker_id) from exc


@router.delete(
    "/workspace/projects/{project_id}/agents/{worker_id}",
    dependencies=[Depends(_require_admin_key)],
)
async def detach_workspace_project_agent(
    project_id: str,
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import detach_project_agent_by_worker_id, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        ok = detach_project_agent_by_worker_id(
            db,
            actor_email=actor,
            project_id=project_id,
            worker_id=worker_id,
        )
    return {"ok": ok}


@router.post("/user-agents", dependencies=[Depends(_require_admin_key)])
async def create_user_agent(
    body: UserAgentCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_agents import create_runtime_agent

    try:
        with open_gateway_db(read_only=False) as db:
            agent = create_runtime_agent(
                db,
                owner_email=actor,
                worker_id=body.worker_id,
                display_name=body.display_name,
                source_template_id=body.source_template_id,
                system_prompt=body.system_prompt,
                description=body.description,
                skills=body.skills,
            )
    except ValueError as exc:
        raise _problem(400, str(exc), body.worker_id) from exc
    return {"agent": agent}
