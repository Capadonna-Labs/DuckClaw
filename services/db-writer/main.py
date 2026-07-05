# services/db-writer/main.py
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

# Multi-Vault: rutas bajo db/ deben resolver igual que el Gateway (cwd suele ser services/db-writer).
_writer_file = Path(__file__).resolve()
_repo_root = _writer_file.parent.parent.parent  # db-writer -> services -> repo
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_repo_root))

import sys
_path_src = str(_repo_root / "packages" / "shared" / "src")
if _path_src not in sys.path:
    sys.path.insert(0, _path_src)

from duckclaw.extensions.state_delta import load_state_delta_handler_bindings

# Resolve extension handlers before built-in handlers register the top-level ``models`` package.
_extension_state_delta_bindings = load_state_delta_handler_bindings()

import duckdb
import redis.asyncio as redis
from context_injection_handler import handle_context_injection_message
from core.config import settings
from db_writer_ops import (
    DbPathLockRegistry,
    push_dlq,
    record_metric,
    run_processing_reclaim_loop,
    run_reliable_queue_loop,
)
try:
    from meditate_state_delta_handler import handle_meditate_state_delta_message
except ImportError:
    handle_meditate_state_delta_message = None

try:
    from reports_state_delta_handler import handle_reports_state_delta_message
except ImportError:
    handle_reports_state_delta_message = None

try:
    from visual_state_delta_handler import handle_visual_state_delta_message
except ImportError:
    handle_visual_state_delta_message = None

try:
    from vlm_state_delta_handler import handle_vlm_state_delta_message
except ImportError:
    handle_vlm_state_delta_message = None

from duckclaw.db_write_queue import (
    TASK_STATUS_TTL_SEC,
    DbWriteTaskStatus,
    task_status_redis_key,
)
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import resolve_user_id_for_db_path

# Configuración de logging robusto
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("db-writer")

_db_path_locks = DbPathLockRegistry()

_TASK_ID_PARTIAL_RE = re.compile(r'"task_id"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"')


def _extract_task_id_partial(message: str) -> str:
    match = _TASK_ID_PARTIAL_RE.search(message)
    if not match:
        return "unknown"
    raw = match.group(1)
    try:
        return str(json.loads(f'"{raw}"'))
    except json.JSONDecodeError:
        return raw


def _ledger_is_completed(conn: duckdb.DuckDBPyConnection, task_id: str) -> bool:
    row = conn.execute(
        "SELECT status FROM main.admin_write_ledger WHERE task_id = ?",
        [task_id],
    ).fetchone()
    return row is not None and row[0] == "completed"


def _ledger_insert_completed(
    conn: duckdb.DuckDBPyConnection,
    task_id: str,
    command_type: str,
    command_json: str,
) -> None:
    conn.execute(
        "INSERT INTO main.admin_write_ledger "
        "(task_id, command_type, command_json, status, created_at) "
        "VALUES (?, ?, ?, 'completed', CURRENT_TIMESTAMP)",
        [task_id, command_type, command_json],
    )


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _connect_duckdb_writable(
    path: str,
    *,
    attempts: int = 12,
    base_sleep_s: float = 0.25,
) -> duckdb.DuckDBPyConnection:
    """
    Abre DuckDB RW con reintentos ante lock del gateway (RO/RW en el mismo archivo).

    During a chat turn the gateway may hold a hub handle; the writer retries
    until the lock clears instead of failing the ledger write.
    """
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return duckdb.connect(path, read_only=False)
        except Exception as exc:
            last = exc
            if _is_duckdb_lock_error(exc):
                delay = base_sleep_s * min(i + 1, 8)
                logger.warning(
                    "db-writer DuckDB lock intento %s/%s, reintento en %.2fs: %s",
                    i + 1,
                    attempts,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


def _run_typed_command_sync(
    task_id: str,
    command_type: str,
    payload: dict,
    target_db_path: str,
) -> str:
    """Ejecuta comando tipado en DuckDB. Retorna 'completed' o 'already_completed'."""
    conn = _connect_duckdb_writable(target_db_path)
    try:
        from duckclaw.schema_migrations import run_pending_migrations

        run_pending_migrations(conn)
        conn.execute("BEGIN TRANSACTION")

        if _ledger_is_completed(conn, task_id):
            conn.execute("ROLLBACK")
            return "already_completed"

        if command_type == "raw_sql":
            query = str(payload.get("query") or "")
            params = payload.get("params", [])
            if not query:
                raise ValueError("No hay query SQL")
            conn.execute(query, params)
        else:
            from duckclaw.write_command_handlers import dispatch_command

            dispatch_command(conn, payload)

        _ledger_insert_completed(
            conn,
            task_id,
            command_type,
            json.dumps(payload, default=str),
        )
        conn.execute("COMMIT")
        return "completed"
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _run_legacy_sql_sync(
    task_id: str,
    query: str,
    params: list,
    target_db_path: str,
    payload: dict,
) -> str:
    """Ejecuta SQL legacy con transacción y ledger. Retorna 'completed' o 'already_completed'."""
    conn = _connect_duckdb_writable(target_db_path)
    try:
        from duckclaw.schema_migrations import run_pending_migrations

        run_pending_migrations(conn)
        conn.execute("BEGIN TRANSACTION")

        if _ledger_is_completed(conn, task_id):
            conn.execute("ROLLBACK")
            return "already_completed"

        conn.execute(query, params)
        _ledger_insert_completed(
            conn,
            task_id,
            "legacy_sql",
            json.dumps(payload, default=str),
        )
        conn.execute("COMMIT")
        return "completed"
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


async def _is_duplicate_task(
    redis_client: redis.Redis,
    task_id: str,
) -> bool:
    """Soft dedup via Redis cache. Durable check against admin_write_ledger
    happens in the transaction itself (INSERT OR REPLACE is safe)."""
    dedup_key = f"dedup:task:{task_id}"
    try:
        was_seen = await redis_client.get(dedup_key)
        return was_seen is not None
    except Exception:
        return False


def _validate_target_db_path(user_id: str, target_db_path: str, tenant_id: str | None) -> str:
    """Validate db_path is accessible for the user. Raises ValueError on failure."""
    resolved = resolve_user_id_for_db_path(user_id, target_db_path, tenant_id=tenant_id)
    if resolved is None:
        raise ValueError("db_path fuera del directorio permitido del usuario")

    try:
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        if path_is_under_shared_tree(target_db_path):
            acl_path = get_gateway_db_path()
            acl_con = duckdb.connect(acl_path, read_only=True)
            try:
                ok_grant = user_may_access_shared_path(
                    acl_con,
                    tenant_id=str(tenant_id or "default").strip() or "default",
                    user_id=resolved,
                    shared_db_path=target_db_path,
                )
            finally:
                acl_con.close()
            if not ok_grant:
                raise ValueError("sin grant de base compartida")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"ACL shared check failed: {exc}") from exc
    return resolved


async def _handle_typed_command(
    redis_client: redis.Redis,
    task_id: str,
    payload: dict,
) -> bool:
    """Process a typed write command. Returns True if handled, False to fall through to legacy."""
    command_type = str(payload.get("command_type") or "").strip()
    if not command_type:
        return False

    dedup_key = f"dedup:task:{task_id}"

    if await _is_duplicate_task(redis_client, task_id):
        logger.info("[%s] Duplicate task skipped (idempotent)", task_id)
        await _publish_task_status(
            redis_client, task_id,
            DbWriteTaskStatus(status="success", detail="already processed"),
        )
        await record_metric(redis_client, "processed")
        return True

    tenant_id = str(payload.get("tenant_id") or "default")
    target_db_path = str(payload.get("db_path") or settings.DUCKDB_PATH)
    user_id = str(payload.get("db_write_user_id") or payload.get("user_id") or "default")

    try:
        user_id = _validate_target_db_path(
            user_id, target_db_path, tenant_id if tenant_id != "default" else None
        )
    except ValueError as exc:
        logger.warning("[%s] Rejected: %s", task_id, exc)
        await _publish_task_status(
            redis_client, task_id,
            DbWriteTaskStatus(status="failed", detail=str(exc)),
        )
        await record_metric(redis_client, "failed")
        return True

    try:
        async with _db_path_locks.acquire(target_db_path):
            outcome = await asyncio.to_thread(
                _run_typed_command_sync,
                task_id,
                command_type,
                payload,
                target_db_path,
            )
    except Exception as exc:
        logger.error("[%s] Typed command %s failed: %s", task_id, command_type, exc)
        await _publish_task_status(
            redis_client, task_id,
            DbWriteTaskStatus(status="failed", detail=str(exc)[:500]),
        )
        await record_metric(redis_client, "failed")
        return True

    if outcome == "already_completed":
        logger.info("[%s] Already completed (ledger dedup)", task_id)
        await _publish_task_status(
            redis_client, task_id,
            DbWriteTaskStatus(status="success", detail="already completed"),
        )
        await redis_client.set(dedup_key, "1", ex=TASK_STATUS_TTL_SEC * 2)
        await record_metric(redis_client, "processed")
        return True

    await redis_client.set(dedup_key, "1", ex=TASK_STATUS_TTL_SEC * 2)
    logger.info("[%s] Command %s completed", task_id, command_type)
    await _publish_task_status(redis_client, task_id, DbWriteTaskStatus(status="success"))
    await record_metric(redis_client, "processed")
    return True


async def _publish_task_status(
    redis_client: redis.Redis,
    task_id: str,
    status: DbWriteTaskStatus,
) -> None:
    try:
        await redis_client.setex(
            task_status_redis_key(task_id),
            TASK_STATUS_TTL_SEC,
            status.model_dump_json(),
        )
    except Exception as exc:
        logger.warning("[%s] No se pudo publicar task_status: %s", task_id, exc)


async def execute_write(redis_client: redis.Redis, message: str) -> None:
    """Ejecuta un comando tipado o query SQL legacy. Confirmación idempotente."""
    task_id = "unknown"
    try:
        payload = json.loads(message)
        task_id = str(payload.get("task_id") or "unknown")

        # Try typed command first
        if await _handle_typed_command(redis_client, task_id, payload):
            return

        # Legacy raw SQL path (payloads sin command_type)
        query = str(payload.get("query") or "")
        params = payload.get("params", [])
        target_db_path = str(payload.get("db_path") or settings.DUCKDB_PATH)
        user_id = str(payload.get("user_id") or "default")
        tenant_raw = payload.get("tenant_id")
        tenant_id = str(tenant_raw).strip() if tenant_raw is not None else None
        if not tenant_id:
            tenant_id = None

        if not query:
            logger.warning("[%s] Payload inválido: No hay query SQL.", task_id)
            await _publish_task_status(
                redis_client,
                task_id,
                DbWriteTaskStatus(status="failed", detail="No hay query SQL"),
            )
            return
        resolved_uid = resolve_user_id_for_db_path(user_id, target_db_path, tenant_id=tenant_id)
        if resolved_uid is None:
            logger.warning("[%s] Rechazado: db_path fuera del directorio permitido del usuario.", task_id)
            await _publish_task_status(
                redis_client,
                task_id,
                DbWriteTaskStatus(status="failed", detail="db_path inválido para el usuario"),
            )
            return
        user_id = resolved_uid

        try:
            from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

            if path_is_under_shared_tree(target_db_path):
                from duckclaw import DuckClaw

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
                    _ac = getattr(acl_con, "_con", None)
                    if _ac is not None:
                        try:
                            _ac.close()
                        except Exception:
                            pass
                if not ok_grant:
                    logger.warning(
                        "[%s] Rechazado: sin grant de base compartida (user=%s).",
                        task_id,
                        user_id,
                    )
                    await _publish_task_status(
                        redis_client,
                        task_id,
                        DbWriteTaskStatus(status="failed", detail="sin grant de base compartida"),
                    )
                    return
        except Exception as exc:
            logger.warning("[%s] ACL shared check failed (fail-closed): %s", task_id, exc)
            await _publish_task_status(
                redis_client,
                task_id,
                DbWriteTaskStatus(status="failed", detail=f"ACL shared check failed: {exc}"[:500]),
            )
            return

        async with _db_path_locks.acquire(target_db_path):
            outcome = await asyncio.to_thread(
                _run_legacy_sql_sync,
                task_id,
                query,
                params,
                target_db_path,
                payload,
            )

        if outcome == "already_completed":
            logger.info("[%s] Legacy SQL already completed (ledger dedup)", task_id)
            await _publish_task_status(
                redis_client,
                task_id,
                DbWriteTaskStatus(status="success", detail="already completed"),
            )
            return

        logger.info("[%s] Escritura exitosa en %s: %s...", task_id, target_db_path, query[:60])
        await _publish_task_status(redis_client, task_id, DbWriteTaskStatus(status="success"))

    except json.JSONDecodeError:
        partial_task_id = _extract_task_id_partial(message)
        logger.error("Error decodificando el mensaje de Redis. Formato JSON inválido.")
        await _publish_task_status(
            redis_client,
            partial_task_id,
            DbWriteTaskStatus(status="failed", detail="Formato JSON inválido"),
        )
    except duckdb.Error as e:
        logger.error("[%s] Error de DuckDB ejecutando la query: %s", task_id, e)
        await _publish_task_status(
            redis_client,
            task_id,
            DbWriteTaskStatus(status="failed", detail=str(e)),
        )
    except Exception as e:
        logger.error("[%s] Error inesperado: %s", task_id, e)
        await _publish_task_status(
            redis_client,
            task_id,
            DbWriteTaskStatus(status="failed", detail=str(e)),
        )


async def _sql_queue_loop(redis_client: redis.Redis) -> None:
    logger.info("Escuchando cola SQL (reliable): %s", settings.QUEUE_NAME)
    await run_reliable_queue_loop(
        redis_client,
        settings.QUEUE_NAME,
        execute_write,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _context_injection_loop(redis_client: redis.Redis) -> None:
    # Debe coincidir con `context_injection_queue_key()` del API Gateway
    # (env DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE o default duckclaw:state_delta:context).
    q = str(settings.CONTEXT_INJECTION_QUEUE_NAME).strip()
    logger.info("Escuchando cola CONTEXT_INJECTION (reliable, delta_type=CONTEXT_INJECTION): %s", q)

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            preview = json.loads(message)
            if str(preview.get("delta_type") or "") != "CONTEXT_INJECTION":
                logger.warning(
                    "Mensaje en cola CONTEXT_INJECTION con delta_type inesperado: %s",
                    preview.get("delta_type"),
                )
        except json.JSONDecodeError:
            logger.warning(
                "CONTEXT_INJECTION payload no es JSON válido (primeros 120 chars): %s",
                message[:120],
            )
        try:
            await handle_context_injection_message(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("CONTEXT_INJECTION handler no capturó excepción: %s", exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _visual_state_delta_loop(redis_client: redis.Redis) -> None:
    if handle_visual_state_delta_message is None:
        logger.warning("VISUAL_STATE_DELTA handler no disponible; omitiendo loop")
        return
    q = str(settings.VISUAL_STATE_DELTA_QUEUE_NAME).strip()
    logger.info("Escuchando cola VISUAL_STATE_DELTA (reliable, VISUAL_ASSET_UPSERT): %s", q)

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            await handle_visual_state_delta_message(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            await push_dlq(redis_client, q, message, str(exc))
            logger.exception("VISUAL_STATE_DELTA handler no capturó excepción: %s", exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _meditate_state_delta_loop(redis_client: redis.Redis) -> None:
    if handle_meditate_state_delta_message is None:
        logger.warning("MEDITATE_STATE_DELTA handler no disponible; omitiendo loop")
        return
    q = str(settings.MEDITATE_STATE_DELTA_QUEUE_NAME).strip()
    logger.info(
        "Escuchando cola MEDITATE_STATE_DELTA (reliable, PURGE_STALE_TASKS, QUARANTINE_MEMORY): %s",
        q,
    )

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            await handle_meditate_state_delta_message(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            await push_dlq(redis_client, q, message, str(exc))
            logger.exception("MEDITATE_STATE_DELTA handler no capturó excepción: %s", exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _reports_state_delta_loop(redis_client: redis.Redis) -> None:
    if handle_reports_state_delta_message is None:
        logger.warning("REPORTS_STATE_DELTA handler no disponible; omitiendo loop")
        return
    q = str(settings.REPORTS_STATE_DELTA_QUEUE_NAME).strip()
    logger.info("Escuchando cola REPORTS_STATE_DELTA (reliable, CUSTOM_REPORT_UPSERT): %s", q)

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            await handle_reports_state_delta_message(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            await push_dlq(redis_client, q, message, str(exc))
            logger.exception("REPORTS_STATE_DELTA handler no capturó excepción: %s", exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _vlm_state_delta_loop(redis_client: redis.Redis) -> None:
    if handle_vlm_state_delta_message is None:
        logger.warning("VLM_STATE_DELTA handler no disponible; omitiendo loop")
        return
    q = str(settings.VLM_STATE_DELTA_QUEUE_NAME).strip()
    logger.info("Escuchando cola VLM_STATE_DELTA (VLM_CONTEXT_EXTRACTED): %s", q)

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            await handle_vlm_state_delta_message(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            await push_dlq(redis_client, q, message, str(exc))
            logger.exception("VLM_STATE_DELTA handler no capturó excepción: %s", exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


async def _extension_state_delta_loop(redis_client: redis.Redis, binding: Any) -> None:
    q = str(binding.queue_name).strip()
    label = str(binding.label or q).strip()
    handler = binding.handler
    logger.info("Escuchando cola extension StateDelta (reliable): %s [%s]", q, label)

    async def _handler(redis_client: redis.Redis, message: str) -> None:
        try:
            await handler(redis_client, message)
        except Exception as exc:  # noqa: BLE001
            await push_dlq(redis_client, q, message, str(exc))
            logger.exception("extension StateDelta handler no capturó excepción [%s]: %s", label, exc)

    await run_reliable_queue_loop(
        redis_client,
        q,
        _handler,
        lease_sec=settings.PROCESSING_LEASE_SEC,
    )


def _all_reliable_queues(extra_bindings: list[Any] | None = None) -> list[str]:
    queues = [
        str(settings.QUEUE_NAME).strip(),
        str(settings.CONTEXT_INJECTION_QUEUE_NAME).strip(),
    ]
    if handle_visual_state_delta_message is not None:
        queues.append(str(settings.VISUAL_STATE_DELTA_QUEUE_NAME).strip())
    if handle_meditate_state_delta_message is not None:
        queues.append(str(settings.MEDITATE_STATE_DELTA_QUEUE_NAME).strip())
    if handle_reports_state_delta_message is not None:
        queues.append(str(settings.REPORTS_STATE_DELTA_QUEUE_NAME).strip())
    if handle_vlm_state_delta_message is not None:
        queues.append(str(settings.VLM_STATE_DELTA_QUEUE_NAME).strip())
    for binding in extra_bindings or ():
        queues.append(str(binding.queue_name).strip())
    return queues


async def process_queue():
    """Consume cola SQL y colas transversales StateDelta en paralelo."""
    extra_bindings = _extension_state_delta_bindings
    redis_client = redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    extension_tasks = [
        _extension_state_delta_loop(redis_client, binding)
        for binding in extra_bindings
    ]
    try:
        await asyncio.gather(
            run_processing_reclaim_loop(
                redis_client,
                _all_reliable_queues(extra_bindings),
                interval_sec=settings.PROCESSING_RECLAIM_INTERVAL_SEC,
            ),
            _sql_queue_loop(redis_client),
            _context_injection_loop(redis_client),
            _visual_state_delta_loop(redis_client),
            _meditate_state_delta_loop(redis_client),
            _reports_state_delta_loop(redis_client),
            _vlm_state_delta_loop(redis_client),
            *extension_tasks,
        )
    except asyncio.CancelledError:
        logger.info("Señal de apagado recibida. Cerrando conexiones...")
    finally:
        await redis_client.aclose()
        logger.info("DB Writer apagado correctamente.")


if __name__ == "__main__":
    logger.info("Iniciando DuckClaw DB Writer...")
    try:
        from startup_bootstrap import run_startup_bootstrap

        run_startup_bootstrap()
        asyncio.run(process_queue())
    except KeyboardInterrupt:
        logger.info("Proceso detenido por el usuario (KeyboardInterrupt).")
