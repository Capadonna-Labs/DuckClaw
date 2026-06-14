from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/templates", tags=["admin-templates"])


class FileWriteBody(BaseModel):
    content: str = ""


class VaultBindingPutBody(BaseModel):
    scope: str = Field(default="", description="private | shared; vacío = quitar binding")
    vault_id: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)


class TemplateCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(default="industries/business_standard")


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
    from routers import admin as admin_router

    return await admin_router._list_templates_impl(include_inactive=include_inactive, actor=actor)


@router.get("/{worker_id}", dependencies=[Depends(require_admin_key)])
async def get_template(
    worker_id: str,
    include_content: bool = True,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._get_template_impl(
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
    from routers import admin as admin_router

    return await admin_router._put_template_file_impl(
        worker_id=worker_id,
        file_path=file_path,
        body=body,
        actor=actor,
    )


@router.get("/{worker_id}/vault-options", dependencies=[Depends(require_admin_key)])
async def template_vault_options(
    worker_id: str,
    vault_user_id: str | None = Query(None, description="ID dueño de db/private/ (default: DUCKCLAW_OWNER_ID)"),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._template_vault_options_impl(
        worker_id=worker_id,
        vault_user_id=vault_user_id,
    )


@router.get("/{worker_id}/vault-binding", dependencies=[Depends(require_admin_key)])
async def get_template_vault_binding(
    worker_id: str,
    vault_user_id: str | None = Query(None),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._get_template_vault_binding_impl(
        worker_id=worker_id,
        vault_user_id=vault_user_id,
    )


@router.put("/{worker_id}/vault-binding", dependencies=[Depends(require_admin_key)])
async def put_template_vault_binding(
    worker_id: str,
    body: VaultBindingPutBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._put_template_vault_binding_impl(
        worker_id=worker_id,
        body=body,
        actor=actor,
    )


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_template(
    body: TemplateCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._create_template_impl(body=body, actor=actor)


@router.delete("/{worker_id}", dependencies=[Depends(require_admin_key)])
async def delete_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._delete_template_impl(worker_id=worker_id, actor=actor)


@router.post("/{worker_id}/reactivate", dependencies=[Depends(require_admin_key)])
async def reactivate_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._reactivate_template_impl(worker_id=worker_id, actor=actor)


@router.delete("/{worker_id}/hard-delete", dependencies=[Depends(require_admin_key)])
async def hard_delete_template(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._hard_delete_template_impl(worker_id=worker_id, actor=actor)


@router.post("/{worker_id}/validate", dependencies=[Depends(require_admin_key)])
async def validate_template(worker_id: str) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._validate_template_impl(worker_id=worker_id)
