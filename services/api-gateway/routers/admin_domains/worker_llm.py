"""Per-worker LLM model: GET the tenant's overrides, PUT one (DB-Writer, fire-and-forget)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.playground.tenant_resolution import gateway_effective_tenant_id

router = APIRouter(tags=["admin-worker-llm"])


class WorkerLlmBody(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=96)
    # OpenRouter model id; empty = inherit the chat's model.
    model: str = Field("", max_length=200)
    tenant_id: str = "default"


@router.get("/worker-llm", dependencies=[Depends(require_admin_key)])
async def list_worker_llm(tenant_id: str = Query("default")) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.worker_llm_overrides import list_worker_llm_models

    tid = gateway_effective_tenant_id(tenant_id)

    def _read() -> dict[str, str]:
        with open_gateway_db(read_only=True) as db:
            return list_worker_llm_models(db, tenant_id=tid)

    return {"tenant_id": tid, "overrides": await asyncio.to_thread(_read)}


@router.put("/worker-llm", dependencies=[Depends(require_admin_key)])
async def set_worker_llm(body: WorkerLlmBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.gateway_enqueue import enqueue_admin_command
    from duckclaw.worker_llm_overrides import WORKER_LLM_DOMAIN, worker_llm_key
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    try:
        key = worker_llm_key(body.worker_id)
    except ValueError as exc:
        raise problem(400, "worker_id inválido", str(exc)) from exc
    tid = gateway_effective_tenant_id(body.tenant_id)
    command = UpsertRuntimeSettingCommand(
        tenant_id=tid,
        actor_email="",
        domain=WORKER_LLM_DOMAIN,
        key=key,
        value=body.model.strip(),
        value_kind="string",
        updated_by=actor,
    )
    try:
        task_id = enqueue_admin_command(command)
    except Exception as exc:
        raise problem(400, "No se pudo guardar el modelo del agente", str(exc)) from exc
    return {"accepted": True, "task_id": task_id, "worker_id": key, "model": body.model.strip(), "tenant_id": tid}
