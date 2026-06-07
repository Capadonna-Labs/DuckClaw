"""DB-first admin routes (catalog import, workspace, user agents)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.admin import _actor_from_header, _admin_audit, _problem, _require_admin_key

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


class OrchestratorDraftBody(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)


class OrchestratorDraftProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)


class OrchestratorDraftWorkerBody(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default="member", max_length=64)
    system_prompt: str = Field(default="", max_length=8000)


class OrchestratorSuggestedSkillBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="", max_length=512)
    available: bool = False


class OrchestratorDraftPayloadBody(BaseModel):
    project: OrchestratorDraftProjectBody
    workers: list[OrchestratorDraftWorkerBody] = Field(default_factory=list, max_length=8)
    shared_context: str = Field(default="", max_length=16000)
    suggested_skills: list[OrchestratorSuggestedSkillBody] = Field(default_factory=list, max_length=16)
    questions: list[str] = Field(default_factory=list, max_length=12)


class OrchestratorConfirmBody(BaseModel):
    draft: OrchestratorDraftPayloadBody


class UserAgentCreateBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    source_template_id: str = "default"
    system_prompt: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class RuntimeSettingPatchItem(BaseModel):
    domain: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    value: Any = ""
    scope: str = "actor"
    value_kind: str = "string"
    secret: bool = False


class RuntimeSettingsPatchBody(BaseModel):
    settings: list[RuntimeSettingPatchItem] = Field(default_factory=list)


def _runtime_setting_scope(item: RuntimeSettingPatchItem, *, actor: str, tenant_id: str) -> tuple[str, str]:
    scope = (item.scope or "actor").strip().lower()
    if scope == "global":
        return "global", ""
    if scope == "tenant":
        return tenant_id, ""
    if scope == "actor":
        return tenant_id, actor
    raise ValueError(f"scope inválido: {item.scope}")


def _orchestrator_title_from_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    cleaned = re.sub(r"^(crear|crea|necesito|quiero|ayudame a crear)\s+", "", text, flags=re.I)
    words = cleaned.split()
    if not words:
        return "Proyecto guiado"
    title = " ".join(words[:6]).strip(" .,:;")
    return title[:1].upper() + title[1:]


def _orchestrator_worker_id_from_project(name: str) -> str:
    from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id

    base = sanitize_catalog_worker_id(name or "guided-agent").replace("_", "-")
    if not base.endswith("-agent"):
        base = f"{base}-agent"
    return base[:64] or "guided-agent"


def _orchestrator_skill_suggestions(db: Any, *, actor_email: str, prompt: str) -> list[dict[str, Any]]:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema

    ensure_admin_worker_catalog_schema(db)
    profile = ensure_profile_for_user(db, email=actor_email)
    rows = db.execute(
        """
        SELECT name, description, implementation_ref
        FROM main.admin_skills
        WHERE active = true
          AND tenant_id IN (?, 'global')
          AND (owner_email = ? OR visibility = 'public')
        ORDER BY name
        """,
        [profile["tenant_id"], profile["email"]],
    )
    prompt_key = (prompt or "").lower()
    suggestions: list[dict[str, Any]] = []
    for name, description, implementation_ref in rows:
        skill_name = str(name or "").strip()
        if not skill_name:
            continue
        tokens = {part for part in re.split(r"[^a-zA-Z0-9]+", skill_name.lower()) if len(part) >= 3}
        desc = str(description or "").strip()
        matched = any(token in prompt_key for token in tokens) or (
            bool(desc) and any(part in prompt_key for part in re.split(r"[^a-zA-Z0-9]+", desc.lower()) if len(part) >= 4)
        )
        if matched:
            suggestions.append(
                {
                    "name": skill_name,
                    "reason": desc or f"Disponible como {implementation_ref}",
                    "available": True,
                }
            )
    if suggestions:
        return suggestions[:6]
    return [
        {
            "name": "project_planning",
            "reason": "Skill sugerida para estructurar objetivos, roles y contexto del proyecto.",
            "available": False,
        }
    ]


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


@router.get("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def list_runtime_settings(
    domain: list[str] | None = Query(None),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_runtime_settings import list_runtime_settings_effective
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        settings = list_runtime_settings_effective(
            db,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            domains=domain or None,
        )
    return {
        "tenant_id": profile["tenant_id"],
        "actor_email": profile["email"],
        "settings": settings,
    }


@router.patch("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def patch_runtime_settings(
    body: RuntimeSettingsPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_resources import record_resource_event
    from duckclaw.admin_runtime_settings import upsert_runtime_setting
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    updated: list[str] = []
    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        for item in body.settings:
            tenant_id, scoped_actor = _runtime_setting_scope(
                item,
                actor=profile["email"],
                tenant_id=profile["tenant_id"],
            )
            value = item.value
            value_json = value if isinstance(value, (dict, list)) else None
            value_text = "" if value_json is not None else str(value or "")
            upsert_runtime_setting(
                db,
                tenant_id=tenant_id,
                actor_email=scoped_actor,
                domain=item.domain,
                key=item.key,
                value_text=value_text,
                value_json=value_json,
                value_kind="json" if value_json is not None else item.value_kind,
                secret=item.secret,
                updated_by=profile["email"],
            )
            domain_key = f"{item.domain.strip().lower()}.{item.key.strip().lower()}"
            updated.append(domain_key)
            record_resource_event(
                db,
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                resource_kind="runtime_setting",
                resource_id=domain_key,
                event_type="runtime_setting.updated",
                payload={"domain": item.domain, "setting": item.key, "scope": item.scope},
            )
    return {"ok": True, "updated": updated}


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


@router.delete("/workspace/projects/{project_id}", dependencies=[Depends(_require_admin_key)])
async def delete_workspace_project(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import deactivate_workspace_project_for_actor, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        ok = deactivate_workspace_project_for_actor(db, actor_email=actor, project_id=project_id)
    if not ok:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    return {"ok": True, "project_id": project_id}


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


@router.post("/workspace/orchestrator/draft", dependencies=[Depends(_require_admin_key)])
async def workspace_orchestrator_draft(
    body: OrchestratorDraftBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import ensure_platform_orchestrator_for_actor

    prompt = body.prompt.strip()
    project_name = _orchestrator_title_from_prompt(prompt)
    with open_gateway_db(read_only=False) as db:
        ensure_platform_orchestrator_for_actor(db, actor_email=actor)
        suggested_skills = _orchestrator_skill_suggestions(db, actor_email=actor, prompt=prompt)
    worker_id = _orchestrator_worker_id_from_project(project_name)
    return {
        "project": {
            "name": project_name,
            "description": prompt[:512],
        },
        "workers": [
            {
                "worker_id": worker_id,
                "display_name": project_name,
                "role": "member",
                "system_prompt": (
                    "Ayuda al usuario a cumplir el objetivo del proyecto usando el contexto compartido, "
                    "preguntando antes de asumir datos faltantes."
                ),
            }
        ],
        "shared_context": f"# Contexto compartido\n\nObjetivo inicial:\n\n{prompt}",
        "suggested_skills": suggested_skills,
        "questions": [
            "¿Qué fuentes de datos debe usar este proyecto?",
            "¿Qué resultado concreto esperas del worker principal?",
            "¿Hay restricciones de tono, seguridad o aprobación humana?",
        ],
    }


@router.post("/workspace/orchestrator/confirm", dependencies=[Depends(_require_admin_key)])
async def workspace_orchestrator_confirm(
    body: OrchestratorConfirmBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import (
        add_worker_context,
        add_worker_version,
        create_worker,
        ensure_platform_orchestrator_for_actor,
        get_visible_worker_for_actor,
    )
    from duckclaw.admin_workspace import (
        attach_agent_to_project,
        create_project as create_workspace_project,
        ensure_admin_workspace_schema,
    )

    draft = body.draft
    created_workers: list[dict[str, Any]] = []
    with open_gateway_db(read_only=False) as db:
        ensure_platform_orchestrator_for_actor(db, actor_email=actor)
        ensure_admin_workspace_schema(db)
        db.execute("BEGIN TRANSACTION")
        try:
            project = create_workspace_project(
                db,
                owner_email=actor,
                name=draft.project.name,
                description=draft.project.description,
            )
            for index, worker_body in enumerate(draft.workers):
                existing = get_visible_worker_for_actor(
                    db,
                    actor_email=actor,
                    worker_id=worker_body.worker_id,
                )
                worker = existing or create_worker(
                    db,
                    owner_email=actor,
                    worker_id=worker_body.worker_id,
                    display_name=worker_body.display_name,
                    source_kind="orchestrator_draft",
                    source_template_id="platform-orchestrator",
                    visibility="private",
                )
                if existing is None:
                    add_worker_version(
                        db,
                        worker_uid=worker["worker_uid"],
                        created_by=actor,
                        manifest_snapshot={
                            "id": worker["worker_id"],
                            "name": worker["display_name"],
                            "description": draft.project.description,
                            "skills": [skill.name for skill in draft.suggested_skills if skill.available],
                        },
                        files_snapshot={
                            "system_prompt.md": worker_body.system_prompt,
                            "soul.md": draft.shared_context,
                        },
                        change_note="Creado desde Platform Orchestrator",
                    )
                if draft.shared_context.strip():
                    add_worker_context(
                        db,
                        worker_uid=worker["worker_uid"],
                        title="Contexto compartido",
                        content_md=draft.shared_context,
                        sort_order=0,
                    )
                attach_agent_to_project(
                    db,
                    project_id=project["project_id"],
                    worker_uid=worker["worker_uid"],
                    role=worker_body.role or "member",
                    sort_order=index,
                )
                created_workers.append(worker)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    _admin_audit(
        "workspace.orchestrator.confirm",
        str(project.get("project_id")),
        str(project.get("name")),
        actor=actor,
        meta={"workers": [worker.get("worker_id") for worker in created_workers]},
    )
    return {"ok": True, "project": project, "created": {"workers": created_workers}}


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
