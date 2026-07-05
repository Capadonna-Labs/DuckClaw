"""Enqueue DuckDB writes without blocking hot paths (gateway / indexer)."""

from __future__ import annotations

import os
from typing import Any

from duckclaw.db_write_queue import DbWriteTaskStatus


def write_poll_timeout_sec() -> float:
    """Optional post-enqueue poll; 0 = fire-and-forget (default for gateway)."""
    raw = (os.environ.get("DUCKCLAW_WRITE_POLL_SEC") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def enqueue_write_command(command: Any, db_path: str, user_id: str) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command

    return enqueue_typed_command(command, db_path=db_path, user_id=user_id)


def wait_write_task(task_id: str, timeout_sec: float = 0) -> DbWriteTaskStatus | None:
    """Poll task_status until timeout; ``timeout_sec=0`` skips poll entirely."""
    if timeout_sec <= 0:
        return None
    from duckclaw.db_write_queue import poll_task_status_sync

    return poll_task_status_sync(task_id, timeout_sec=timeout_sec)


def resolve_write_enqueue_result(
    task_id: str,
    status: DbWriteTaskStatus | None,
) -> tuple[bool, str]:
    """Map enqueue + optional status to ``(ok, user_message)``."""
    if status is None:
        if write_poll_timeout_sec() <= 0:
            return True, f"Write encolado (task_id={task_id})"
        return False, "timeout esperando db-writer"
    if status.status != "success":
        return False, (status.detail or "db-writer failed")[:500]
    return True, ""


def enqueue_write_and_resolve(
    command: Any,
    *,
    db_path: str,
    user_id: str,
) -> tuple[bool, str]:
    """Enqueue typed command; optionally wait per ``DUCKCLAW_WRITE_POLL_SEC``."""
    task_id = enqueue_write_command(command, db_path=db_path, user_id=user_id)
    status = wait_write_task(task_id, timeout_sec=write_poll_timeout_sec())
    return resolve_write_enqueue_result(task_id, status)
