"""
Cooperative chat interrupt: Redis flag checked by LangGraph nodes during long turns.

Used when the admin UI (or HTTP client disconnect) requests cancellation; asyncio.Task.cancel
alone does not stop graph.invoke() running in a worker thread.

Two interrupt channels:
- **chat cancel** (user / SSE): ``request_chat_cancel`` — admin SSE aborts the whole turn.
- **graph interrupt** (internal): ``request_graph_interrupt`` — stops an orphan worker graph
  after a wall-clock timeout without aborting the parent SSE / manager replan loop.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_CHAT_CANCEL_PREFIX = "duckclaw:chat_cancel:"
_GRAPH_INTERRUPT_PREFIX = "duckclaw:graph_interrupt:"
_CHAT_CANCEL_TTL_SECONDS = 300
_LOCAL_CANCEL_LOCK = threading.Lock()
_LOCAL_CANCEL_UNTIL: dict[str, float] = {}
_LOCAL_INTERRUPT_LOCK = threading.Lock()
_LOCAL_INTERRUPT_UNTIL: dict[str, float] = {}


class ChatCancelledError(Exception):
    """Raised when chat cancel or graph interrupt was requested for this session."""


def _redis_url() -> str:
    return (
        (os.environ.get("DUCKCLAW_WRITE_QUEUE_URL") or "").strip()
        or (os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    )


def chat_cancel_redis_key(chat_id: str) -> str:
    cid = str(chat_id or "").strip() or "unknown"
    return f"{_CHAT_CANCEL_PREFIX}{cid}"


def graph_interrupt_redis_key(chat_id: str) -> str:
    cid = str(chat_id or "").strip() or "unknown"
    return f"{_GRAPH_INTERRUPT_PREFIX}{cid}"


def _local_mark(store: dict[str, float], lock: threading.Lock, chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    until = time.time() + float(_CHAT_CANCEL_TTL_SECONDS)
    with lock:
        store[cid] = until


def _local_clear(store: dict[str, float], lock: threading.Lock, chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    with lock:
        store.pop(cid, None)


def _local_active(store: dict[str, float], lock: threading.Lock, chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    now = time.time()
    with lock:
        until = store.get(cid)
        if until is None:
            return False
        if until < now:
            store.pop(cid, None)
            return False
        return True


def _redis_setex(key: str) -> None:
    url = _redis_url()
    if not url:
        return
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.setex(key, _CHAT_CANCEL_TTL_SECONDS, "1")
    except Exception:
        pass


def _redis_delete(key: str) -> None:
    url = _redis_url()
    if not url:
        return
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _redis_exists(key: str) -> bool:
    url = _redis_url()
    if not url:
        return False
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        return bool(client.get(key))
    except Exception:
        return False


def request_chat_cancel(chat_id: str) -> bool:
    """Set user/SSE cancel flag (idempotent). Always marks in-process; Redis when configured."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    _local_mark(_LOCAL_CANCEL_UNTIL, _LOCAL_CANCEL_LOCK, cid)
    _redis_setex(chat_cancel_redis_key(cid))
    return True


def clear_chat_cancel(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    _local_clear(_LOCAL_CANCEL_UNTIL, _LOCAL_CANCEL_LOCK, cid)
    _redis_delete(chat_cancel_redis_key(cid))


def is_chat_cancel_requested(chat_id: str) -> bool:
    """User/SSE cancel only — admin SSE watches this to abort the whole turn."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    if _local_active(_LOCAL_CANCEL_UNTIL, _LOCAL_CANCEL_LOCK, cid):
        return True
    return _redis_exists(chat_cancel_redis_key(cid))


def request_graph_interrupt(chat_id: str) -> bool:
    """
    Stop an orphan worker graph after wall-clock timeout without aborting parent SSE.

    Worker nodes check this via ``raise_if_chat_cancelled``; admin SSE must NOT treat it
    as a user interrupt (that previously yielded empty ``(sin respuesta)`` turns).
    """
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    _local_mark(_LOCAL_INTERRUPT_UNTIL, _LOCAL_INTERRUPT_LOCK, cid)
    _redis_setex(graph_interrupt_redis_key(cid))
    return True


def clear_graph_interrupt(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    _local_clear(_LOCAL_INTERRUPT_UNTIL, _LOCAL_INTERRUPT_LOCK, cid)
    _redis_delete(graph_interrupt_redis_key(cid))


def is_graph_interrupt_requested(chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    if _local_active(_LOCAL_INTERRUPT_UNTIL, _LOCAL_INTERRUPT_LOCK, cid):
        return True
    return _redis_exists(graph_interrupt_redis_key(cid))


def raise_if_chat_cancelled(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    if is_chat_cancel_requested(cid):
        raise ChatCancelledError(f"Chat interrupted: {cid}")
    if is_graph_interrupt_requested(cid):
        raise ChatCancelledError(f"Graph interrupted: {cid}")
