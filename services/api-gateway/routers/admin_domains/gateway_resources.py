"""Admin endpoints to release in-process Gateway resources."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Header

from routers.admin_domains.admin_common import admin_audit, actor_from_header, require_admin_key

router = APIRouter(tags=["admin-gateway-resources"])


@router.post("/gateway/release-worker-cache", dependencies=[Depends(require_admin_key)])
async def release_worker_cache(
    x_actor: str | None = Header(None, alias="X-Duckclaw-Actor"),
) -> dict[str, Any]:
    """Vacía caché LangGraph en el proceso Gateway (no reinicia PM2)."""
    from duckclaw.ops.gateway_resource_release import release_worker_graph_cache

    actor = actor_from_header(x_actor)
    result = await asyncio.to_thread(release_worker_graph_cache, force=True)
    admin_audit(
        "gateway.release_worker_cache",
        "worker_graph_cache",
        f"entries {result.get('entries_before')}→{result.get('entries_after')}",
        actor=actor,
        meta=result,
    )
    return result
