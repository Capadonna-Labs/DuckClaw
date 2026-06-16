from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(tags=["admin-template-contexts"])


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


def _enqueue_template_context_command(command: Any) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        detail = command_status.detail or "template context write failed"
        if "No hay query SQL" in detail:
            raise ValueError(
                "DB-Writer desactualizado: reinicia DuckClaw-DB-Writer y DuckClaw-Gateway para aplicar comandos de templates."
            )
        raise ValueError(detail)
    return task_id


def _visible_worker(worker_id: str, actor: str) -> dict[str, str]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import get_visible_worker_for_actor

    with open_gateway_db(read_only=True) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise _problem(404, "Worker no visible en catálogo", worker_id)
    return {
        "worker_uid": str(worker["worker_uid"]),
        "tenant_id": str(worker.get("tenant_id") or "default"),
    }


@router.post("/templates/import", dependencies=[Depends(require_admin_key)])
async def import_templates_to_catalog(
    body: TemplateImportBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import ImportTemplatesToCatalogCommand

    try:
        command = ImportTemplatesToCatalogCommand(
            actor_email=actor,
            templates_root=body.templates_root,
            include_prefixes=body.include_prefixes,
            include_template_ids=body.include_template_ids,
        )
        task_id = _enqueue_template_context_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), "templates/import") from exc
    return {"ok": True, "task_id": task_id}


@router.post("/templates/{worker_id}/contexts", dependencies=[Depends(require_admin_key)])
async def create_template_context(
    worker_id: str,
    body: TemplateContextBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertWorkerContextCommand

    worker = _visible_worker(worker_id, actor)
    try:
        command = UpsertWorkerContextCommand(
            actor_email=actor,
            tenant_id=worker["tenant_id"],
            worker_uid=worker["worker_uid"],
            title=body.title,
            content_md=body.content_md,
            sort_order=body.sort_order,
        )
        task_id = _enqueue_template_context_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), worker_id) from exc
    return {"ok": True, "task_id": task_id, "worker_uid": worker["worker_uid"]}


@router.patch("/templates/{worker_id}/contexts/reorder", dependencies=[Depends(require_admin_key)])
async def reorder_template_contexts(
    worker_id: str,
    body: ContextReorderBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import ReorderWorkerContextsCommand

    worker = _visible_worker(worker_id, actor)
    try:
        command = ReorderWorkerContextsCommand(
            actor_email=actor,
            tenant_id=worker["tenant_id"],
            worker_uid=worker["worker_uid"],
            items=body.items,
        )
        task_id = _enqueue_template_context_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), worker_id) from exc
    return {"ok": True, "task_id": task_id, "worker_uid": worker["worker_uid"]}


@router.delete("/templates/{worker_id}/contexts/{context_id}", dependencies=[Depends(require_admin_key)])
async def delete_template_context(
    worker_id: str,
    context_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import DeactivateWorkerContextCommand

    worker = _visible_worker(worker_id, actor)
    try:
        command = DeactivateWorkerContextCommand(
            actor_email=actor,
            tenant_id=worker["tenant_id"],
            worker_uid=worker["worker_uid"],
            context_id=context_id,
        )
        task_id = _enqueue_template_context_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), context_id) from exc
    return {"ok": True, "task_id": task_id, "worker_uid": worker["worker_uid"], "context_id": context_id}
