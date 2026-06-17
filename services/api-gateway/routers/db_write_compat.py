"""DEPRECATED transitional router for legacy raw-SQL writes.

Prefer typed ``WriteCommand`` payloads enqueued via ``duckclaw.db_write_queue``
and handled by ``duckclaw.write_handlers`` in the singleton ``db-writer`` process.
This module remains only for backward-compatible ``POST /api/v1/db/write`` callers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.gateway_acl_db import get_gateway_acl_duckdb
from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved
from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path
from duckclaw.vaults import resolve_active_vault, validate_user_db_path, vault_scope_id_for_tenant


router = APIRouter()


class WriteRequest(BaseModel):
    query: str = Field(..., description="Consulta SQL parametrizada")
    params: list[Any] = Field(default_factory=list, description="Parámetros para la consulta")
    tenant_id: str = Field(default="default", description="ID del tenant")
    user_id: str | None = Field(default=None, description="ID del usuario dueño de la bóveda")
    db_path: str | None = Field(default=None, description="Ruta DuckDB destino (bóveda activa)")


class EnqueueResponse(BaseModel):
    status: str
    task_id: str


def _resolve_db_path_for_write(req: WriteRequest, user_id: str, tenant_id: str | None) -> str:
    db_path = (req.db_path or "").strip()
    if db_path:
        return db_path
    dedicated_db_path = dedicated_gateway_db_path_resolved()
    if dedicated_db_path:
        return dedicated_db_path
    effective_tenant = str(tenant_id or "default").strip() or "default"
    _, active_vault_path = resolve_active_vault(user_id, vault_scope_id_for_tenant(effective_tenant))
    return active_vault_path


def _assert_write_path_allowed(req: WriteRequest, user_id: str, tenant_id: str | None, db_path: str) -> None:
    if not (req.db_path or "").strip():
        return
    if not validate_user_db_path(user_id, db_path, tenant_id=tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="db_path inválido para el usuario.",
        )
    if not path_is_under_shared_tree(db_path):
        return
    if user_may_access_shared_path(
        get_gateway_acl_duckdb()[0],
        tenant_id=str(tenant_id or "default").strip() or "default",
        user_id=user_id,
        shared_db_path=db_path,
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Sin permiso para escribir en esta base de datos compartida.",
    )


@router.post("/api/v1/db/write", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_write(req: WriteRequest, request: Request) -> EnqueueResponse:
    """Encola escrituras legacy raw SQL para el DB Writer."""
    if req.query.strip().upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las consultas SELECT deben ejecutarse directamente, no encolarse.",
        )
    task_id = str(uuid.uuid4())
    user_id = (req.user_id or "").strip() or "default"
    tenant_id = (req.tenant_id or "").strip() or None
    db_path = _resolve_db_path_for_write(req, user_id, tenant_id)
    _assert_write_path_allowed(req, user_id, tenant_id, db_path)
    # DB-first compat allowlist: /api/v1/db/write is the legacy raw SQL queue
    # endpoint used by singleton-writer compatibility and smoke pipelines.
    # Prefer typed WriteCommand payloads for structured admin mutations.
    payload = {
        "task_id": task_id,
        "tenant_id": req.tenant_id,
        "user_id": user_id,
        "db_path": db_path,
        "query": req.query,
        "params": req.params,
    }
    try:
        await request.app.state.redis.lpush("duckdb_write_queue", json.dumps(payload))
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error conectando al broker de mensajes: {str(exc)}",
        ) from exc
    return EnqueueResponse(status="enqueued", task_id=task_id)
