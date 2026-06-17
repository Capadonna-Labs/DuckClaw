"""Bootstrap filesystem de workers/plantillas vía ``POST /projects`` (legacy wizard)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import (
    actor_from_header,
    admin_audit,
    problem,
    repo_root,
    require_admin_key,
)
from routers.admin_domains.template_lifecycle import create_worker_from_source

router = APIRouter(tags=["admin-project-bootstrap"])


class ProjectCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(
        default="default",
        description="Preset de habilidades (id de plantilla opcional). El disco siempre clona desde templates/default.",
    )
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    topology: str = "general"
    system_prompt: str = ""
    soul: str = ""


@router.post("/projects", dependencies=[Depends(require_admin_key)])
async def create_project(
    body: ProjectCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.id.strip())
    if not wid:
        raise problem(400, "id inválido", body.id)
    dest = create_worker_from_source(
        wid=wid,
        source_template=body.source_template,
        name=body.name,
        description=body.description,
        skills=body.skills,
        topology=body.topology,
        system_prompt=body.system_prompt,
        soul=body.soul,
    )
    admin_audit(
        "project.create",
        f"templates/{wid}",
        body.source_template,
        actor=actor,
        meta={"skills": body.skills, "path": str(dest.relative_to(repo_root()))},
    )
    return {"ok": True, "id": wid, "path": str(dest.relative_to(repo_root()))}
