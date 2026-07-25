"""Fire-and-forget DB writes from Gateway — no blocking poll on the event loop."""

from __future__ import annotations

from typing import Any


def enqueue_admin_command(command: Any, *, user_id: str = "default") -> str:
    """Enqueue typed write; Gateway must not poll synchronously."""
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path

    return enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id=user_id)


def get_write_task_status(task_id: str) -> dict[str, Any] | None:
    """Read db-writer confirmation from Redis (``task_status:{id}``). None if still pending."""
    from duckclaw.db_write_queue import DbWriteTaskStatus, get_task_status_sync

    tid = (task_id or "").strip()
    if not tid:
        return None
    row = get_task_status_sync(tid)
    if row is None:
        return None
    return {
        "task_id": tid,
        "status": row.status,
        "detail": row.detail,
    }
