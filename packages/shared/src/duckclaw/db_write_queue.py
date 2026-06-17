"""
Cola singleton de escrituras DuckDB (Redis) y confirmación por task_id.

Usado por admin_sql (poll), db-writer (SET task_status) y fallbacks de escritura controlados.
En perfil Spawn sin db-writer, ``enqueue_duckdb_write_sync`` aplica SQL en proceso.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel, Field

from duckclaw.spawn_profile import spawn_inline_writes_enabled

_log = logging.getLogger(__name__)

TASK_STATUS_KEY_PREFIX = "task_status:"
TASK_STATUS_TTL_SEC = 60
DEFAULT_WRITE_QUEUE_NAME = "duckdb_write_queue"
LEGACY_WRITE_QUEUE_URL_ENV = "DUCKCLAW_WRITE_QUEUE_URL"
LEGACY_DB_PATH_ENV = "DUCKCLAW_DB_PATH"
_WRITE_SQL_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "REPLACE", "ALTER", "DROP", "TRUNCATE")


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


def _is_write_sql(sql: str) -> bool:
    """Return True for SQL statements that must go through the singleton writer."""
    statement = (sql or "").strip().upper()
    return any(statement.startswith(prefix) for prefix in _WRITE_SQL_PREFIXES)


def _legacy_default_db_path(db_path: str | None) -> str:
    target = str(db_path or "").strip()
    if target:
        return target

    legacy_env = (os.environ.get(LEGACY_DB_PATH_ENV) or "").strip()
    if legacy_env:
        from duckclaw.gateway_db import resolve_env_duckdb_path

        return resolve_env_duckdb_path(legacy_env)

    from duckclaw.gateway_db import get_gateway_db_path

    return get_gateway_db_path()


def enqueue_write(sql: str, db_path: str | None = None) -> bool:
    """Compatibility adapter for legacy raw SQL callers.

    The canonical queue payload is still produced by ``enqueue_duckdb_write_sync``;
    this wrapper only preserves the old bool-returning API.
    """
    query = (sql or "").strip()
    if not query or not _is_write_sql(query):
        return False

    try:
        enqueue_duckdb_write_sync(
            db_path=_legacy_default_db_path(db_path),
            query=query,
            params=[],
            user_id="default",
            tenant_id="default",
            queue_name=DEFAULT_WRITE_QUEUE_NAME,
            redis_url=(os.environ.get(LEGACY_WRITE_QUEUE_URL_ENV) or "").strip() or None,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        _log.debug("legacy singleton enqueue skipped: %s", exc)
        return False


def execute_write_direct(db: Any, sql: str) -> None:
    """Execute SQL directly inside a singleton writer consumer process."""
    db.execute(sql)


class WriteQueueBridge:
    """Legacy ``db.execute`` wrapper that routes writes through ``db_write_queue``."""

    def __init__(self, db: Any, db_path: str | None = None):
        self._db = db
        self._db_path = db_path

    def execute(self, sql: str) -> None:
        if not _is_write_sql(sql):
            self._db.execute(sql)
            return
        if enqueue_write(sql, self._db_path):
            return
        if spawn_inline_writes_enabled():
            self._db.execute(sql)
            return
        raise RuntimeError("DuckDB writes must be enqueued through duckclaw.db_write_queue")

    def query(self, sql: str) -> Any:
        return self._db.query(sql)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def run_consumer(db_path: str | None = None, poll_interval: float = 0.5) -> None:
    """Legacy CLI consumer kept for import compatibility.

    Production deployments should run ``services/db-writer/main.py``; this helper
    remains a singleton consumer for old ``python -m`` invocations.
    """
    queue_url = (os.environ.get(LEGACY_WRITE_QUEUE_URL_ENV) or "").strip() or redis_url_from_env()
    path = _legacy_default_db_path(db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    from duckclaw import DuckClaw

    db = DuckClaw(path)
    try:
        import redis
    except ImportError:
        print("redis no instalado. pip install redis", file=sys.stderr)
        sys.exit(1)

    client = redis.from_url(queue_url)
    print(f"DuckClaw-DB-Writer iniciado. DB: {path}", flush=True)
    while True:
        try:
            item = client.brpop(DEFAULT_WRITE_QUEUE_NAME, timeout=int(poll_interval))
            if not item:
                time.sleep(0.01)
                continue
            _, raw = item
            data = json.loads(raw)
            query = str(data.get("query") or data.get("sql") or "").strip()
            params = data.get("params") or []
            if query:
                if params:
                    db.execute(query, params)
                else:
                    execute_write_direct(db, query)
                print(f"OK: {query[:80]}...", flush=True)
        except json.JSONDecodeError:
            pass
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
        time.sleep(0.01)


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


def _resolve_enqueue_user_id(
    *,
    user_id: str,
    target_db_path: str,
    tenant_id: str,
) -> str:
    from duckclaw.vaults import resolve_user_id_for_db_path

    resolved = resolve_user_id_for_db_path(
        user_id,
        target_db_path,
        tenant_id=tenant_id or None,
    )
    if resolved is None:
        raise ValueError("db_path inválido para el usuario")
    return resolved


def _validate_write_target(
    *,
    user_id: str,
    target_db_path: str,
    tenant_id: str,
) -> None:
    _resolve_enqueue_user_id(
        user_id=user_id,
        target_db_path=target_db_path,
        tenant_id=tenant_id,
    )

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
    tid_tenant = str(tenant_id or "default").strip() or "default"
    uid = _resolve_enqueue_user_id(
        user_id=str(user_id or "default").strip() or "default",
        target_db_path=target,
        tenant_id=tid_tenant,
    )
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
    redis_url: str | None = None,
) -> str:
    """Encola ``RawSqlCommand`` tipado (compat legacy). Devuelve task_id."""
    _ = redis_url
    from duckclaw.write_commands import RawSqlCommand

    tid = task_id or str(uuid.uuid4())
    tid_tenant = str(tenant_id or "default").strip() or "default"
    uid = _resolve_enqueue_user_id(
        user_id=str(user_id or "default").strip() or "default",
        target_db_path=str(db_path or "").strip(),
        tenant_id=tid_tenant,
    )
    command = RawSqlCommand(
        task_id=tid,
        query=query,
        params=list(params or []),
        db_path=str(db_path or ""),
        user_id=uid,
        tenant_id=tid_tenant,
    )
    return enqueue_typed_command(
        command,
        db_path=db_path,
        user_id=uid,
        queue_name=queue_name,
    )


def enqueue_typed_command(
    command: Any,
    *,
    db_path: str,
    user_id: str = "default",
    queue_name: str = DEFAULT_WRITE_QUEUE_NAME,
) -> str:
    """Enqueue a typed WriteCommand to Redis (or apply inline in Spawn profile).

    Returns task_id. The command payload is enriched with ``db_path``,
    ``user_id`` and ``tenant_id`` so the db-writer resolves the correct
    target database and validates ACLs.
    """
    tid = command.task_id
    payload_raw = command.to_redis_payload()
    import json as _json

    enriched = _json.loads(payload_raw)
    producer_user_id = str(user_id or "default")
    enriched["db_path"] = str(db_path or "")
    if str(enriched.get("user_id") or "").strip():
        enriched["db_write_user_id"] = producer_user_id
    else:
        enriched["user_id"] = producer_user_id
        enriched["db_write_user_id"] = producer_user_id
    enriched["tenant_id"] = enriched.get("tenant_id") or str(command.tenant_id or "default")
    payload = _json.dumps(enriched, ensure_ascii=False)

    if spawn_inline_writes_enabled():
        _validate_write_target(
            user_id=str(enriched.get("db_write_user_id") or enriched.get("user_id") or "default"),
            target_db_path=str(db_path or ""),
            tenant_id=str(enriched["tenant_id"]),
        )
        import duckdb

        conn = duckdb.connect(db_path, read_only=False)
        status = DbWriteTaskStatus(status="success")
        _raised: BaseException | None = None
        try:
            from duckclaw.schema_migrations import run_pending_migrations

            run_pending_migrations(conn)
            conn.execute("BEGIN TRANSACTION")
            from duckclaw.write_command_handlers import dispatch_command

            dispatch_command(conn, enriched)
            conn.execute(
                "INSERT INTO main.admin_write_ledger "
                "(task_id, command_type, command_json, status, created_at) "
                "VALUES (?, ?, ?, 'completed', CURRENT_TIMESTAMP)",
                [tid, enriched.get("command_type", ""), payload],
            )
            conn.execute("COMMIT")
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            status = DbWriteTaskStatus(status="failed", detail=str(exc)[:500])
            _raised = exc
        finally:
            conn.close()
            try:
                _publish_inline_task_status(tid, status)
            except Exception:
                pass
        if _raised is not None:
            raise _raised
        return tid

    import redis

    r = redis.from_url(redis_url_from_env(), decode_responses=True)
    r.lpush(queue_name, payload)
    return tid


def enqueue_or_apply_duckdb_write_sync(
    *,
    db_path: str,
    command: Any | None = None,
    query: str | None = None,
    params: list[Any] | None = None,
    user_id: str = "default",
    tenant_id: str = "default",
    task_id: str | None = None,
    queue_name: str = DEFAULT_WRITE_QUEUE_NAME,
) -> str:
    """Enqueue a typed command or legacy raw SQL. Typed commands preferred."""
    if command is not None:
        return enqueue_typed_command(
            command, db_path=db_path, user_id=user_id, queue_name=queue_name,
        )
    if not query:
        raise ValueError("query required when no typed command provided")
    return enqueue_duckdb_write_sync(
        db_path=db_path, query=query, params=params,
        user_id=user_id, tenant_id=tenant_id,
        task_id=task_id, queue_name=queue_name,
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
