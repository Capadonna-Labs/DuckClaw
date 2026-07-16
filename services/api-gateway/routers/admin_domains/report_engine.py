"""Report Engine admin routes — templates, Word instances, preview, progress."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(tags=["admin-report-engine"])


def _actor_profile(actor: str) -> dict[str, str]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
    return {"tenant_id": str(profile["tenant_id"]), "email": str(profile["email"])}


def _enqueue_report_command(payload: dict[str, Any], *, actor_email: str) -> str:
    from duckclaw.db_write_queue import enqueue_dict_command
    from duckclaw.gateway_db import get_gateway_db_path

    return enqueue_dict_command(
        payload,
        db_path=get_gateway_db_path(),
        user_id=actor_email or "default",
    )


class RegisterReportTemplateBody(BaseModel):
    template_docx_path: str = Field(..., min_length=1)
    name: str = ""
    description: str = ""
    visibility: str = "private"
    template_id: str = ""


class CreateReportInstanceBody(BaseModel):
    template_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    project_id: str = ""
    # period_key intentionally omitted from product contract (legacy ignored if sent)


@router.get("/report-templates", dependencies=[Depends(require_admin_key)])
async def list_report_templates_route(
    limit: int = 50,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.report_engine.admin_report_read import list_report_templates

    profile = _actor_profile(actor)
    with open_gateway_db(read_only=True) as db:
        templates = list_report_templates(
            db,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            limit=limit,
        )
    return {"templates": templates, "count": len(templates)}


@router.post("/report-templates/register", dependencies=[Depends(require_admin_key)])
async def register_report_template_route(
    body: RegisterReportTemplateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path
    from duckclaw.report_engine.analyzer import analyze_docx_template, normalize_analyzer_mode_for_storage

    profile = _actor_profile(actor)
    try:
        source = resolve_readable_document_path(relative_path=body.template_docx_path.strip())
        analysis = analyze_docx_template(source)
    except ValueError as exc:
        raise problem(400, str(exc), "report_template") from exc

    storage_mode = normalize_analyzer_mode_for_storage(str(analysis.get("analyzer_mode") or "jinja"))

    tid = (body.template_id or "").strip() or f"rtpl_{uuid.uuid4().hex[:10]}"
    name = (body.name or "").strip() or source.stem
    task_id = _enqueue_report_command(
        {
            "command_type": "upsert_report_template",
            "template_id": tid,
            "tenant_id": profile["tenant_id"],
            "actor_email": profile["email"],
            "name": name,
            "description": (body.description or "").strip(),
            "template_uri": str(source),
            "section_schema": analysis.get("sections") or [],
            "analyzer_mode": storage_mode,
            "visibility": (body.visibility or "private").strip(),
        },
        actor_email=profile["email"],
    )
    return {
        "ok": True,
        "task_id": task_id,
        "template_id": tid,
        "name": name,
        "section_count": len(analysis.get("sections") or []),
        "sections": analysis.get("sections") or [],
        "tables": analysis.get("tables") or [],
        "fields_in_tables": analysis.get("fields_in_tables", 0),
        "analyzer_mode": analysis.get("analyzer_mode"),
        "storage_analyzer_mode": storage_mode,
    }


@router.post("/report-instances", dependencies=[Depends(require_admin_key)])
async def create_report_instance_route(
    body: CreateReportInstanceBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    iid = f"rpt_{uuid.uuid4().hex[:10]}"
    try:
        task_id = _enqueue_report_command(
            {
                "command_type": "create_report_instance",
                "instance_id": iid,
                "template_id": body.template_id.strip(),
                "tenant_id": profile["tenant_id"],
                "actor_email": profile["email"],
                "title": body.title.strip(),
                "period_key": "",
                "project_id": (body.project_id or "").strip(),
            },
            actor_email=profile["email"],
        )
    except ValueError as exc:
        raise problem(400, str(exc), "report_instance") from exc
    return {
        "ok": True,
        "task_id": task_id,
        "instance_id": iid,
        "template_id": body.template_id.strip(),
        "title": body.title.strip(),
        "status": "draft",
    }


@router.get("/report-instances", dependencies=[Depends(require_admin_key)])
async def list_report_instances_route(
    project_id: str = "",
    limit: int = 50,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.report_engine.admin_report_read import list_report_instances

    profile = _actor_profile(actor)
    with open_gateway_db(read_only=True) as db:
        instances = list_report_instances(
            db,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=project_id,
            limit=limit,
        )
    return {"instances": instances, "count": len(instances)}


@router.get("/report-instances/{instance_id}", dependencies=[Depends(require_admin_key)])
async def get_report_instance_route(
    instance_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
        get_report_template,
    )
    from duckclaw.report_engine.state import summarize_status

    profile = _actor_profile(actor)
    iid = (instance_id or "").strip()
    if not iid:
        raise problem(400, "instance_id requerido", "report_instance")

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        instance = get_report_instance(db, instance_id=iid, tenant_id=profile["tenant_id"])
        if not instance:
            raise problem(404, "Instancia no encontrada", "report_instance")
        if not actor_can_access_instance(db, instance=instance, actor_email=profile["email"]):
            raise HTTPException(status_code=403, detail="Acceso denegado")
        template = get_report_template(
            db, template_id=str(instance["template_id"]), tenant_id=profile["tenant_id"]
        )
        schema = (template or {}).get("section_schema") or []
        progress = summarize_status(instance["state"], schema)

    return {
        "instance": instance,
        "template_name": (template or {}).get("name") or "",
        "progress": progress,
    }


@router.delete("/report-instances/{instance_id}", dependencies=[Depends(require_admin_key)])
async def soft_delete_report_instance_route(
    instance_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )

    profile = _actor_profile(actor)
    iid = (instance_id or "").strip()
    if not iid:
        raise problem(400, "instance_id requerido", "report_instance")

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        instance = get_report_instance(db, instance_id=iid, tenant_id=profile["tenant_id"])
        if not instance:
            raise problem(404, "Instancia no encontrada", "report_instance")
        if not actor_can_access_instance(db, instance=instance, actor_email=profile["email"]):
            raise HTTPException(status_code=403, detail="Acceso denegado")

    task_id = _enqueue_report_command(
        {
            "command_type": "soft_delete_report_instance",
            "instance_id": iid,
            "tenant_id": profile["tenant_id"],
            "actor_email": profile["email"],
        },
        actor_email=profile["email"],
    )
    return {"ok": True, "task_id": task_id, "instance_id": iid, "status": "archived"}


@router.delete("/report-templates/{template_id}", dependencies=[Depends(require_admin_key)])
async def soft_delete_report_template_route(
    template_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.report_engine.admin_report_read import get_report_template

    profile = _actor_profile(actor)
    tid = (template_id or "").strip()
    if not tid:
        raise problem(400, "template_id requerido", "report_template")

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        template = get_report_template(db, template_id=tid, tenant_id=profile["tenant_id"])
        if not template:
            raise problem(404, "Plantilla no encontrada", "report_template")
        owner = str(template.get("owner_email") or "").strip().lower()
        if owner != profile["email"].strip().lower():
            raise HTTPException(status_code=403, detail="Solo el propietario puede eliminar la plantilla")

    task_id = _enqueue_report_command(
        {
            "command_type": "soft_delete_report_template",
            "template_id": tid,
            "tenant_id": profile["tenant_id"],
            "actor_email": profile["email"],
        },
        actor_email=profile["email"],
    )
    return {"ok": True, "task_id": task_id, "template_id": tid, "status": "archived"}


@router.get(
    "/report-instances/{instance_id}/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_admin_key)],
)
async def report_instance_preview_route(
    instance_id: str,
    actor: str = Depends(actor_from_header),
) -> HTMLResponse:
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
    )

    profile = _actor_profile(actor)
    iid = (instance_id or "").strip()
    if not iid:
        raise problem(400, "instance_id requerido", "report_instance")

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        instance = get_report_instance(db, instance_id=iid, tenant_id=profile["tenant_id"])
        if not instance:
            raise problem(404, "Instancia no encontrada", "report_instance")
        if not actor_can_access_instance(db, instance=instance, actor_email=profile["email"]):
            raise HTTPException(status_code=403, detail="Acceso denegado")
        html = str(instance.get("preview_html") or "").strip()

    if not html:
        html = """<!DOCTYPE html><html><body style="font-family:system-ui;padding:2rem;color:#64748b">
<h3>Sin vista previa</h3>
<p>Continúa el informe en el Chat: pide rellenar las secciones pendientes y generar el Word final.</p>
</body></html>"""
    return HTMLResponse(content=html)
