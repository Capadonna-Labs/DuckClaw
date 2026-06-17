from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(prefix="/forge-projects", tags=["admin-forge-projects"])


class ForgeProjectCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=48)
    display_name: str = Field(default="", max_length=128)
    members: list[str] = Field(default_factory=list)
    coordinator: str | None = Field(default=None, max_length=64)
    shared_vault_id: str | None = Field(default=None, max_length=64)
    shared_context: str = Field(default="", max_length=32_000)
    apply_tenant_team: bool = Field(default=False)
    tenant_id: str = Field(default="default", max_length=64)


class ForgeProjectPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    members: list[str] | None = None
    coordinator: str | None = Field(default=None, max_length=64)
    shared_vault_id: str | None = Field(default=None, max_length=64)
    shared_context: str | None = Field(default=None, max_length=32_000)


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_forge_projects() -> dict[str, Any]:
    raise problem(
        410,
        "Forge Projects legacy retirado",
        "Usa /workspace/projects y el flujo administrado de workspace DB-first.",
    )


@router.get("/env-presets", dependencies=[Depends(require_admin_key)])
async def forge_project_env_presets() -> dict[str, Any]:
    raise problem(
        410,
        "Presets DUCKCLAW_TEAM_* retirados",
        "Usa proyectos DB-first y asignaciones admin_project_agents.",
    )


@router.get("/{slug}", dependencies=[Depends(require_admin_key)])
async def get_forge_project(slug: str) -> dict[str, Any]:
    raise problem(410, "Forge Projects legacy retirado", slug)


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_forge_project(
    body: ForgeProjectCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Forge Projects legacy retirado",
        "Crea proyectos desde /workspace/projects o el flujo administrado de workspace.",
    )


@router.patch("/{slug}", dependencies=[Depends(require_admin_key)])
async def patch_forge_project(
    slug: str,
    body: ForgeProjectPatchBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(410, "Forge Projects legacy retirado", slug)


@router.delete("/{slug}", dependencies=[Depends(require_admin_key)])
async def delete_forge_project(
    slug: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(410, "Forge Projects legacy retirado", slug)


@router.post("/{slug}/apply-team", dependencies=[Depends(require_admin_key)])
async def apply_forge_project_team(
    slug: str,
    tenant_id: str = Query("default"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Team templates legacy retirado",
        "Usa admin_project_agents en Proyectos DB-first.",
    )
