"""Operaciones compartidas del db-writer: DLQ, métricas, locks y cola reliable."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import redis.asyncio as redis

logger = logging.getLogger("db-writer.ops")

DLQ_SUFFIX = ":dlq"
PROCESSING_SUFFIX = ":processing"
LEASE_KEY_PREFIX = "db_writer:processing:lease:"


def processing_queue_key(source_queue: str) -> str:
    return f"{source_queue.rstrip()}{PROCESSING_SUFFIX}"


def processing_lease_key(source_queue: str) -> str:
    return f"{LEASE_KEY_PREFIX}{source_queue.rstrip()}"


async def push_dlq(
    redis_client: redis.Redis,
    source_queue: str,
    message: str,
    error: str,
    *,
    handler: str = "",
) -> None:
    """Encola mensaje fallido en la DLQ derivada de la cola origen."""
    dlq_key = f"{source_queue.rstrip()}{DLQ_SUFFIX}"
    payload = {
        "source_queue": source_queue,
        "message": message,
        "error": (error or "")[:2000],
        "ts": int(time.time()),
    }
    if handler:
        payload["handler"] = handler
    try:
        await redis_client.lpush(dlq_key, json.dumps(payload, ensure_ascii=False))
        logger.warning("DLQ: encolado en %s", dlq_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DLQ: LPUSH falló en %s: %s", dlq_key, exc)


async def record_metric(redis_client: redis.Redis, name: str, delta: int = 1) -> None:
    """Incrementa contador db_writer:metric:{name}."""
    key = f"db_writer:metric:{name}"
    try:
        await redis_client.incrby(key, delta)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo registrar métrica %s: %s", key, exc)


class DbPathLockRegistry:
    """Un asyncio.Lock por ruta DuckDB normalizada (serializa escrituras concurrentes)."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    @staticmethod
    def _normalize_path(db_path: str) -> str:
        return str(Path(db_path).resolve())

    @asynccontextmanager
    async def acquire(self, db_path: str) -> AsyncIterator[None]:
        normalized = self._normalize_path(db_path)
        async with self._registry_lock:
            if normalized not in self._locks:
                self._locks[normalized] = asyncio.Lock()
            path_lock = self._locks[normalized]
        async with path_lock:
            yield


async def reclaim_processing_on_startup(
    redis_client: redis.Redis,
    source_queue: str,
) -> int:
    """Tras crash: devuelve mensajes en :processing a la cola principal."""
    processing = processing_queue_key(source_queue)
    lease_key = processing_lease_key(source_queue)
    reclaimed = 0
    while True:
        message = await redis_client.rpop(processing)
        if message is None:
            break
        await redis_client.lpush(source_queue, message)
        await redis_client.zrem(lease_key, message)
        reclaimed += 1
    if reclaimed:
        logger.warning(
            "Reclaimed %s stale in-flight message(s) from %s → %s",
            reclaimed,
            processing,
            source_queue,
        )
        await record_metric(redis_client, "reclaimed", reclaimed)
    return reclaimed


async def register_processing_lease(
    redis_client: redis.Redis,
    source_queue: str,
    message: str,
    *,
    lease_sec: int,
) -> None:
    deadline = time.time() + max(1, lease_sec)
    await redis_client.zadd(processing_lease_key(source_queue), {message: deadline})


async def ack_processing_message(
    redis_client: redis.Redis,
    source_queue: str,
    message: str,
) -> None:
    processing = processing_queue_key(source_queue)
    removed = await redis_client.lrem(processing, 1, message)
    await redis_client.zrem(processing_lease_key(source_queue), message)
    if removed == 0:
        logger.warning("ACK miss on %s (message not in processing list)", processing)


async def pop_reliable_message(
    redis_client: redis.Redis,
    source_queue: str,
    *,
    block_timeout: int = 0,
) -> str | None:
    """BRPOPLPUSH atómico: mueve mensaje a :processing sin perderlo en crash."""
    processing = processing_queue_key(source_queue)
    return await redis_client.brpoplpush(source_queue, processing, timeout=block_timeout)


async def reclaim_expired_processing_leases(
    redis_client: redis.Redis,
    source_queue: str,
) -> int:
    """Reencola mensajes cuyo lease expiró (worker colgado, no solo crash)."""
    lease_key = processing_lease_key(source_queue)
    processing = processing_queue_key(source_queue)
    now = time.time()
    expired = await redis_client.zrangebyscore(lease_key, 0, now)
    if not expired:
        return 0
    count = 0
    for message in expired:
        removed = await redis_client.lrem(processing, 1, message)
        if removed:
            await redis_client.lpush(source_queue, message)
            count += 1
        await redis_client.zrem(lease_key, message)
    if count:
        logger.warning(
            "Reclaimed %s expired lease message(s) for queue %s",
            count,
            source_queue,
        )
        await record_metric(redis_client, "reclaimed", count)
    return count


async def run_reliable_queue_loop(
    redis_client: redis.Redis,
    source_queue: str,
    handler: Callable[[redis.Redis, str], Awaitable[None]],
    *,
    lease_sec: int,
) -> None:
    """Consume cola con BRPOPLPUSH + ACK; handler debe capturar errores si aplica DLQ."""
    await reclaim_processing_on_startup(redis_client, source_queue)
    while True:
        message = await pop_reliable_message(redis_client, source_queue, block_timeout=0)
        if not message:
            continue
        await register_processing_lease(redis_client, source_queue, message, lease_sec=lease_sec)
        try:
            await handler(redis_client, message)
        finally:
            await ack_processing_message(redis_client, source_queue, message)


async def run_processing_reclaim_loop(
    redis_client: redis.Redis,
    queues: list[str],
    *,
    interval_sec: int,
) -> None:
    """Tarea de fondo: reencola leases expirados en todas las colas."""
    while True:
        await asyncio.sleep(max(1, interval_sec))
        for queue in queues:
            try:
                await reclaim_expired_processing_leases(redis_client, queue)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reclaim loop error for %s: %s", queue, exc)
