"""Report Engine admin routes — Word instances, preview, progress."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(tags=["admin-report-engine"])


def _actor_profile(actor: str) -> dict[str, str]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
    return {"tenant_id": str(profile["tenant_id"]), "email": str(profile["email"])}


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
<p>Pide al agente que complete secciones con <code>patch_report_section</code> o ejecuta <code>render_report_instance</code>.</p>
</body></html>"""
    return HTMLResponse(content=html)
