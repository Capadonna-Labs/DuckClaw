"""Mutex por chat_id vía Redis para serializar invocaciones concurrentes."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def chat_lock(redis_client: Any, chat_id: str):
    """
    Mutex por chat_id usando Redis (si está disponible).

    - Clave: lock:chat:{chat_id}
    - timeout: evita locks huérfanos si el proceso muere durante la ejecución.
    - blocking_timeout: tiempo máximo esperando el lock antes de soltar y continuar.
    """
    if redis_client is None:
        yield
        return
    lock_key = f"lock:chat:{chat_id}"
    lock = redis_client.lock(lock_key, timeout=10, blocking_timeout=15)
    acquired = False
    try:
        acquired = await lock.acquire()
        yield
    finally:
        if acquired:
            try:
                await lock.release()
            except Exception:
                pass


def chat_parallel_invocations_enabled() -> bool:
    """
    Si True, no se serializa por chat_id: varios POST concurrentes (p. ej. Telegram)
    pueden ejecutar el grafo a la vez.

    ``CHAT_PARALLEL_INVOCATIONS`` es alias de ``DUCKCLAW_CHAT_PARALLEL_INVOCATIONS``.
    """
    for key in ("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS", "CHAT_PARALLEL_INVOCATIONS"):
        if (os.environ.get(key) or "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


@asynccontextmanager
async def maybe_chat_lock(redis_client: Any, chat_id: str):
    if chat_parallel_invocations_enabled():
        yield
        return
    async with chat_lock(redis_client, chat_id):
        yield


@asynccontextmanager
async def maybe_chat_lock_for_request(redis_client: Any, chat_id: str, skip_session_lock: bool):
    """Evita lock de sesión para tareas internas (p. ej. SUMMARIZE_NEW_CONTEXT)."""
    if skip_session_lock:
        yield
        return
    async with maybe_chat_lock(redis_client, chat_id):
        yield
