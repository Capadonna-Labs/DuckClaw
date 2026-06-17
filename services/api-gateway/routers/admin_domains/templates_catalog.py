from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from duckclaw import db_write_queue
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.write_commands import (
    DeactivateCatalogWorkerCommand,
    HardDeleteCatalogWorkerCommand,
    ReactivateCatalogWorkerCommand,
    UpdateCatalogWorkerFileCommand,
)
from routers.admin_domains.template_lifecycle import (
    FileWriteBody,
    TemplateCreateBody,
    VaultBindingPutBody,
    create_template_impl,
    get_template_impl,
    get_template_vault_binding_impl,
    list_templates_impl,
    put_template_vault_binding_impl,
    template_vault_options_impl,
    validate_template_impl,
)

router = APIRouter(prefix="/templates", tags=["admin-templates"])


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _template_worker_id(worker_id: str) -> str:
    wid = (worker_id or "").strip()
    if not wid:
        raise _problem(400, "worker_id requerido", "templates")
    if wid == "default" or wid in {"entry_router", "manager_router"}:
        raise _problem(403, "Plantilla protegida", wid)
    return wid


def _enqueue_template_catalog_command(command: Any) -> str:
    task_id = db_write_queue.enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5, interval_sec=0.05)
    if command_status and command_status.status == "failed":
        detail = command_status.detail or "template catalog write failed"
        raise _problem(400, "Mutación de template rechazada por DB-writer", detail)
    return task_id


def _admin_audit(action: str, resource: str, detail: str, *, actor: str, task_id: str) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta={"task_id": task_id})


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    from routers import admin as admin_router

    admin_router._require_admin_key(x_admin_key)


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    from routers import admin as admin_router

    return admin_router._actor_from_header(x_actor)


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_templates(
    include_inactive: bool = Query(False),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return await list_templates_impl(include_inactive=include_inactive, actor=actor)


@router.get("/{worker_id}", dependencies=[Depends(require_admin_key)])
async def get_template(
    worker_id: str,
    include_content: bool = True,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return await get_template_impl(
        worker_id=worker_id,
        include_content=include_content,
        actor=actor,
    )


@router.put("/{worker_id}/files/{file_path:path}", dependencies=[Depends(require_admin_key)])
async def put_template_file(
    worker_id: str,
    file_path: str,
    body: FileWriteBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    wid = _template_worker_id(worker_id)
    command = UpdateCatalogWorkerFileCommand(
        actor_email=actor,
        worker_id=wid,
        file_path=file_path,
        content=body.content,
    )
    task_id = _enqueue_template_catalog_command(command)
    _admin_audit(
        "template.file.put",
        f"templates/{wid}",
        file_path,
        actor=actor,
        task_id=task_id,
    )
    return {
        "ok": True,
        "path": file_path,
        "source": "catalog",
        "task_id": task_id,
    }


@router.get("/{worker_id}/vault-options", dependencies=[Depends(require_admin_key)])
async def template_vault_options(
    worker_id: str,
    vault_user_id: str | None = Query(None, description="ID dueño de db/private/ (default: DUCKCLAW_OWNER_ID)"),
) -> dict[str, Any]:
    return await template_vault_options_impl(
        worker_id=worker_id,
        vault_user_id=vault_user_id,
    )


@router.get("/{worker_id}/vault-binding", dependencies=[Depends(require_admin_key)])
async def get_template_vault_binding(
    worker_id: str,
    vault_user_id: str | None = Query(None),
) -> dict[str, Any]:
    return await get_template_vault_binding_impl(
        worker_id=worker_id,
        vault_user_id=vault_user_id,
    )


@router.put("/{worker_id}/vault-binding", dependencies=[Depends(require_admin_key)])
async def put_template_vault_binding(
    worker_id: str,
    body: VaultBindingPutBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return await put_template_vault_binding_impl(
        worker_id=worker_id,
        body=body,
        actor=actor,
    )


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_template(
    body: TemplateCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    return await create_template_impl(body=body, actor=actor)


@router.delete("/{worker_id}", dependencies=[Depends(require_admin_key)])
async def delete_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    wid = _template_worker_id(worker_id)
    command = DeactivateCatalogWorkerCommand(actor_email=actor, worker_id=wid)
    task_id = _enqueue_template_catalog_command(command)
    _admin_audit(
        "template.delete",
        f"templates/{wid}",
        "catalog_deactivate",
        actor=actor,
        task_id=task_id,
    )
    return {"ok": True, "id": wid, "action": "deactivated", "task_id": task_id}


@router.post("/{worker_id}/reactivate", dependencies=[Depends(require_admin_key)])
async def reactivate_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    wid = _template_worker_id(worker_id)
    command = ReactivateCatalogWorkerCommand(actor_email=actor, worker_id=wid)
    task_id = _enqueue_template_catalog_command(command)
    _admin_audit(
        "template.reactivate",
        f"templates/{wid}",
        "catalog_reactivate",
        actor=actor,
        task_id=task_id,
    )
    return {"ok": True, "id": wid, "action": "reactivated", "task_id": task_id}


@router.delete("/{worker_id}/hard-delete", dependencies=[Depends(require_admin_key)])
async def hard_delete_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    wid = _template_worker_id(worker_id)
    command = HardDeleteCatalogWorkerCommand(actor_email=actor, worker_id=wid)
    task_id = _enqueue_template_catalog_command(command)
    _admin_audit(
        "template.hard_delete",
        f"templates/{wid}",
        "catalog_hard_delete",
        actor=actor,
        task_id=task_id,
    )
    return {"ok": True, "id": wid, "hard_deleted": True, "task_id": task_id}


@router.post("/{worker_id}/validate", dependencies=[Depends(require_admin_key)])
async def validate_template(worker_id: str) -> dict[str, Any]:
    return await validate_template_impl(worker_id=worker_id)
