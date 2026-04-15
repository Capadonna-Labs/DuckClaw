# services/db-writer/main.py
import asyncio
import json
import logging
import os
from pathlib import Path

# Multi-Vault: rutas bajo db/ deben resolver igual que el Gateway (cwd suele ser services/db-writer).
_writer_file = Path(__file__).resolve()
_repo_root = _writer_file.parent.parent.parent  # db-writer -> services -> repo
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_repo_root))

import duckdb
import redis.asyncio as redis
from context_injection_handler import handle_context_injection_message
from core.config import settings
from duckclaw.db_write_queue import (
    TASK_STATUS_TTL_SEC,
    DbWriteTaskStatus,
    task_status_redis_key,
)
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.vaults import validate_user_db_path

# Configuración de logging robusto
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("db-writer")


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
    """Ejecuta la consulta SQL de forma segura y confirma en Redis."""
    task_id = "unknown"
    target_db_path = ""
    query = ""
    try:
        payload = json.loads(message)
        task_id = str(payload.get("task_id") or "unknown")
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
        if not validate_user_db_path(user_id, target_db_path, tenant_id=tenant_id):
            logger.warning("[%s] Rechazado: db_path fuera del directorio permitido del usuario.", task_id)
            await _publish_task_status(
                redis_client,
                task_id,
                DbWriteTaskStatus(status="failed", detail="db_path inválido para el usuario"),
            )
            return

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
            logger.warning("[%s] ACL shared check skipped/failed: %s", task_id, exc)

        def _exec() -> None:
            conn_local = duckdb.connect(target_db_path, read_only=False)
            try:
                conn_local.execute(query, params)
            finally:
                conn_local.close()

        await asyncio.to_thread(_exec)

        logger.info("[%s] Escritura exitosa en %s: %s...", task_id, target_db_path, query[:60])
        await _publish_task_status(redis_client, task_id, DbWriteTaskStatus(status="success"))

    except json.JSONDecodeError:
        logger.error("Error decodificando el mensaje de Redis. Formato JSON inválido.")
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
    logger.info("Escuchando cola SQL: %s", settings.QUEUE_NAME)
    while True:
        result = await redis_client.brpop(settings.QUEUE_NAME, timeout=0)
        if result:
            _, message = result
            await execute_write(redis_client, message)


async def _context_injection_loop(redis_client: redis.Redis) -> None:
    # Debe coincidir con `context_injection_queue_key()` del API Gateway
    # (env DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE o default duckclaw:state_delta:context).
    q = str(settings.CONTEXT_INJECTION_QUEUE_NAME).strip()
    logger.info("Escuchando cola CONTEXT_INJECTION (delta_type=CONTEXT_INJECTION): %s", q)
    while True:
        result = await redis_client.brpop(q, timeout=0)
        if result:
            _, message = result
            try:
                preview = json.loads(message)
                if str(preview.get("delta_type") or "") != "CONTEXT_INJECTION":
                    logger.warning(
                        "Mensaje en cola CONTEXT_INJECTION con delta_type inesperado: %s",
                        preview.get("delta_type"),
                    )
            except json.JSONDecodeError:
                logger.warning("CONTEXT_INJECTION payload no es JSON válido (primeros 120 chars): %s", message[:120])
            try:
                await handle_context_injection_message(redis_client, message)
            except Exception as exc:  # noqa: BLE001
                logger.exception("CONTEXT_INJECTION handler no capturó excepción: %s", exc)


async def process_queue():
    """Consume cola SQL y cola CONTEXT_INJECTION en paralelo."""
    redis_client = redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    try:
        await asyncio.gather(
            _sql_queue_loop(redis_client),
            _context_injection_loop(redis_client),
        )
    except asyncio.CancelledError:
        logger.info("Señal de apagado recibida. Cerrando conexiones...")
    finally:
        await redis_client.aclose()
        logger.info("DB Writer apagado correctamente.")


if __name__ == "__main__":
    logger.info("Iniciando DuckClaw DB Writer...")
    try:
        asyncio.run(process_queue())
    except KeyboardInterrupt:
        logger.info("Proceso detenido por el usuario (KeyboardInterrupt).")
