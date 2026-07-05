"""Async status for admin DB writes (no blocking poll in Gateway)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from routers.admin_domains.admin_common import require_admin_key

router = APIRouter(tags=["admin-write-tasks"])


@router.get("/write-tasks/{task_id}", dependencies=[Depends(require_admin_key)])
async def get_admin_write_task(task_id: str) -> dict[str, Any]:
    from duckclaw.gateway_enqueue import get_write_task_status

    row = get_write_task_status(task_id)
    if row is None:
        return {"task_id": task_id.strip(), "status": "pending", "detail": None}
    return row
