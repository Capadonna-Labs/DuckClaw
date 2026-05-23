"""
Cola singleton de escrituras DuckDB (Redis) y confirmación por task_id.

Usado por admin_sql (poll), db-writer (SET task_status), y war rooms en modo RO.
En perfil Spawn sin db-writer, ``enqueue_duckdb_write_sync`` aplica SQL en proceso.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field

from duckclaw.spawn_profile import spawn_inline_writes_enabled

_log = logging.getLogger(__name__)

TASK_STATUS_KEY_PREFIX = "task_status:"
TASK_STATUS_TTL_SEC = 60
DEFAULT_WRITE_QUEUE_NAME = "duckdb_write_queue"


class DbWriteTaskStatus(BaseModel):
    """Estado publicado por db-writer tras ejecutar (o fallar) una escritura."""

    status: Literal["success", "failed"]
    detail: str | None = Field(default=None)


def redis_url_from_env() -> str:
    from duckclaw.runtime_env import resolve_redis_url

    return resolve_redis_url()


def task_status_redis_key(task_id: str) -> str:
    return f"{TASK_STATUS_KEY_PREFIX}{task_id}"


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg or "different configuration" in msg


def _connect_duckdb_writable_with_retry(
    path: str,
    *,
    attempts: int = 12,
    base_sleep_s: float = 0.25,
) -> duckdb.DuckDBPyConnection:
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_duckdb_lock_error(exc) and i + 1 < attempts:
                time.sleep(base_sleep_s * min(i + 1, 8))
                continue
            raise
    assert last is not None
    raise last


def _validate_write_target(
    *,
    user_id: str,
    target_db_path: str,
    tenant_id: str,
) -> None:
    from duckclaw.vaults import validate_user_db_path

    if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id or None):
        raise ValueError("db_path inválido para el usuario")

    try:
        from duckclaw import DuckClaw
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        if path_is_under_shared_tree(target_db_path):
            acl_path = get_gateway_db_path()
            acl_con = DuckClaw(acl_path, read_only=True)
            try:
                ok_grant = user_may_access_shared_path(
                    acl_con,
                    tenant_id=str(tenant_id or "default").strip() or "default",
                    user_id=user_id,
                    shared_db_path=target_db_path,
                )
            finally:
                try:
                    acl_con.close()
                except Exception:
                    pass
            if not ok_grant:
                raise ValueError("sin grant de base compartida")
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.warning("ACL shared check skipped/failed: %s", exc)


def apply_duckdb_write_sync(
    *,
    db_path: str,
    query: str,
    params: list[Any] | None = None,
    user_id: str = "default",
    tenant_id: str = "default",
    task_id: str | None = None,
) -> str:
    """Ejecuta SQL en DuckDB RW (perfil Spawn). Devuelve task_id."""
    tid = task_id or str(uuid.uuid4())
    q = (query or "").strip()
    if not q:
        raise ValueError("No hay query SQL")
    target = str(db_path or "").strip()
    if not target:
        raise ValueError("db_path vacío")
    uid = str(user_id or "default").strip() or "default"
    tid_tenant = str(tenant_id or "default").strip() or "default"
    _validate_write_target(user_id=uid, target_db_path=target, tenant_id=tid_tenant)
    try:
        con = _connect_duckdb_writable_with_retry(target)
        try:
            con.execute(q, list(params or []))
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        _publish_inline_task_status(tid, DbWriteTaskStatus(status="failed", detail=str(exc)[:500]))
        raise
    _publish_inline_task_status(tid, DbWriteTaskStatus(status="success"))
    return tid


def _publish_inline_task_status(task_id: str, status: DbWriteTaskStatus) -> None:
    """Compatibilidad con callers que hacen poll tras enqueue (p. ej. vault RO efímero)."""
    try:
        import redis

        r = redis.from_url(redis_url_from_env(), decode_responses=True)
        r.setex(
            task_status_redis_key(task_id),
            TASK_STATUS_TTL_SEC,
            status.model_dump_json(),
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("inline task_status publish skipped: %s", exc)


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
    """LPUSH del payload JSON, o apply inline en perfil Spawn. Devuelve task_id."""
    if spawn_inline_writes_enabled():
        return apply_duckdb_write_sync(
            db_path=db_path,
            query=query,
            params=params,
            user_id=user_id,
            tenant_id=tenant_id,
            task_id=task_id,
        )

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


def enqueue_or_apply_duckdb_write_sync(
    *,
    db_path: str,
    query: str,
    params: list[Any] | None = None,
    user_id: str = "default",
    tenant_id: str = "default",
    task_id: str | None = None,
    queue_name: str = DEFAULT_WRITE_QUEUE_NAME,
) -> str:
    """Alias explícito de ``enqueue_duckdb_write_sync`` (cola o inline según perfil)."""
    return enqueue_duckdb_write_sync(
        db_path=db_path,
        query=query,
        params=params,
        user_id=user_id,
        tenant_id=tenant_id,
        task_id=task_id,
        queue_name=queue_name,
    )


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
