"""
Cola singleton de escrituras DuckDB (Redis) y confirmación por task_id.

Usado por admin_sql (poll), db-writer (SET task_status), y war rooms en modo RO.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

TASK_STATUS_KEY_PREFIX = "task_status:"
TASK_STATUS_TTL_SEC = 60
DEFAULT_WRITE_QUEUE_NAME = "duckdb_write_queue"


class DbWriteTaskStatus(BaseModel):
    """Estado publicado por db-writer tras ejecutar (o fallar) una escritura."""

    status: Literal["success", "failed"]
    detail: str | None = Field(default=None)


def redis_url_from_env() -> str:
    return (
        os.environ.get("REDIS_URL")
        or os.environ.get("DUCKCLAW_REDIS_URL")
        or "redis://localhost:6379/0"
    ).strip()


def task_status_redis_key(task_id: str) -> str:
    return f"{TASK_STATUS_KEY_PREFIX}{task_id}"


def enqueue_duckdb_write_sync(
    *,
    db_path: str,
    query: str,
    params: list[Any] | None = None,
    user_id: str = "default",
    tenant_id: str = "default",
    task_id: str | None = None,
    queue_name: str = DEFAULT_WRITE_QUEUE_NAME,
) -> str:
    """LPUSH del payload JSON. Devuelve task_id."""
    import redis

    tid = task_id or str(uuid.uuid4())
    payload = {
        "task_id": tid,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "db_path": db_path,
        "query": query,
        "params": list(params or []),
    }
    r = redis.from_url(redis_url_from_env(), decode_responses=True)
    r.lpush(queue_name, json.dumps(payload))
    return tid


def poll_task_status_sync(
    task_id: str,
    *,
    timeout_sec: float = 3.0,
    interval_sec: float = 0.05,
) -> DbWriteTaskStatus | None:
    """GET task_status:<id> hasta timeout. None si no hubo confirmación."""
    import redis

    r = redis.from_url(redis_url_from_env(), decode_responses=True)
    key = task_status_redis_key(task_id)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        raw = r.get(key)
        if raw:
            try:
                return DbWriteTaskStatus.model_validate_json(raw)
            except Exception:
                pass
        time.sleep(interval_sec)
    return None
