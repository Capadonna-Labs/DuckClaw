"""Operaciones compartidas del db-writer: DLQ, métricas y locks por ruta DuckDB."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import redis.asyncio as redis

logger = logging.getLogger("db-writer.ops")

DLQ_SUFFIX = ":dlq"


async def push_dlq(
    redis_client: redis.Redis,
    source_queue: str,
    message: str,
    error: str,
) -> None:
    """Encola mensaje fallido en la DLQ derivada de la cola origen."""
    dlq_key = f"{source_queue.rstrip()}{DLQ_SUFFIX}"
    payload = {
        "source_queue": source_queue,
        "message": message,
        "error": (error or "")[:2000],
        "ts": int(time.time()),
    }
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
