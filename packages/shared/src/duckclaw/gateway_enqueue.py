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
    import redis

    from duckclaw.db_write_queue import DbWriteTaskStatus, task_status_redis_key
    from duckclaw.runtime_env import resolve_redis_url

    tid = (task_id or "").strip()
    if not tid:
        return None
    client = redis.from_url(resolve_redis_url(), decode_responses=True)
    raw = client.get(task_status_redis_key(tid))
    if not raw:
        return None
    try:
        row = DbWriteTaskStatus.model_validate_json(raw)
    except Exception:
        return None
    return {
        "task_id": tid,
        "status": row.status,
        "detail": row.detail,
    }
