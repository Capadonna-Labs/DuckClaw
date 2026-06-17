"""Rutas agente: listado de workers e historial Redis por sesión."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

from core.chat_history import (
    gateway_chat_history_enabled,
    history_redis_key,
    redis_load_chat_history,
)
from duckclaw.forge.team_env import default_tenant_id_from_runtime, default_worker_id_from_env

router = APIRouter(tags=["agent"])


def effective_tenant_id(request_tenant: str | None) -> str:
    """
    Tenant efectivo para Redis, whitelist y logs.

    Si el cliente envía un tenant explícito distinto del placeholder ``default``, ese valor gana.
    Si solo llega ``default`` u omisión, aplica env explícito, runtime settings DB-first o ``default``.
    """
    rt = (request_tenant or "").strip()
    if rt and rt.lower() != "default":
        return rt
    return default_tenant_id_from_runtime()


@router.get("/api/v1/agent/workers")
async def agent_workers():
    try:
        from duckclaw.workers.factory import list_workers

        workers = list_workers()
        return {"workers": workers}
    except Exception:
        return {"workers": [default_worker_id_from_env()]}


@router.get("/api/v1/agent/{worker_id}/history")
async def agent_history(
    request: Request,
    worker_id: str,
    session_id: str | None = None,
    chat_id: str | None = None,
    tenant_id: str | None = None,
):
    """
    Historial persistido en Redis (mismas claves que ``POST .../chat`` cuando no se envía ``history``).

    Usar el mismo ``session_id`` / ``chat_id`` que en el chat y el mismo tenant.
    """
    redis_client = getattr(request.app.state, "redis", None)
    sid = (
        (session_id or "").strip()
        or (chat_id or "").strip()
        or (request.headers.get("X-Chat-Id") or "").strip()
        or (request.headers.get("X-Session-Id") or "").strip()
        or "default"
    )
    tid_src = (tenant_id or "").strip() or (request.headers.get("X-Tenant-Id") or "").strip() or None
    tid = effective_tenant_id(tid_src)
    hist = await redis_load_chat_history(redis_client, tid, sid)
    out: dict[str, Any] = {
        "history": hist,
        "worker_id": worker_id,
        "tenant_id": tid,
        "session_id": sid,
    }
    if (os.environ.get("DUCKCLAW_GATEWAY_HISTORY_DEBUG") or "").strip().lower() in ("1", "true", "yes"):
        out["redis_key"] = history_redis_key(tid, sid)
        out["redis_connected"] = redis_client is not None
        out["gateway_chat_history_enabled"] = gateway_chat_history_enabled()
    return out
