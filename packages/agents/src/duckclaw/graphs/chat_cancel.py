"""
Cooperative chat interrupt: Redis flag checked by LangGraph nodes during long turns.

Used when the admin UI (or HTTP client disconnect) requests cancellation; asyncio.Task.cancel
alone does not stop graph.invoke() running in a worker thread.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_CHAT_CANCEL_PREFIX = "duckclaw:chat_cancel:"
_CHAT_CANCEL_TTL_SECONDS = 300
_LOCAL_CANCEL_LOCK = threading.Lock()
_LOCAL_CANCEL_UNTIL: dict[str, float] = {}


class ChatCancelledError(Exception):
    """Raised when ``request_chat_cancel`` was called for this chat session."""


def _redis_url() -> str:
    return (
        (os.environ.get("DUCKCLAW_WRITE_QUEUE_URL") or "").strip()
        or (os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    )


def chat_cancel_redis_key(chat_id: str) -> str:
    cid = str(chat_id or "").strip() or "unknown"
    return f"{_CHAT_CANCEL_PREFIX}{cid}"


def _local_cancel_mark(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    until = time.time() + float(_CHAT_CANCEL_TTL_SECONDS)
    with _LOCAL_CANCEL_LOCK:
        _LOCAL_CANCEL_UNTIL[cid] = until


def _local_cancel_clear(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    with _LOCAL_CANCEL_LOCK:
        _LOCAL_CANCEL_UNTIL.pop(cid, None)


def _local_cancel_active(chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    now = time.time()
    with _LOCAL_CANCEL_LOCK:
        until = _LOCAL_CANCEL_UNTIL.get(cid)
        if until is None:
            return False
        if until < now:
            _LOCAL_CANCEL_UNTIL.pop(cid, None)
            return False
        return True


def request_chat_cancel(chat_id: str) -> bool:
    """Set cancel flag (idempotent). Always marks in-process; Redis when configured."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    _local_cancel_mark(cid)
    url = _redis_url()
    if not url:
        return True
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.setex(chat_cancel_redis_key(cid), _CHAT_CANCEL_TTL_SECONDS, "1")
        return True
    except Exception:
        return True


def clear_chat_cancel(chat_id: str) -> None:
    cid = str(chat_id or "").strip()
    if not cid:
        return
    _local_cancel_clear(cid)
    url = _redis_url()
    if not url:
        return
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(chat_cancel_redis_key(cid))
    except Exception:
        pass


def is_chat_cancel_requested(chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    if _local_cancel_active(cid):
        return True
    url = _redis_url()
    if not url:
        return False
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        val = client.get(chat_cancel_redis_key(cid))
        return bool(val)
    except Exception:
        return False


def raise_if_chat_cancelled(chat_id: str) -> None:
    if is_chat_cancel_requested(chat_id):
        raise ChatCancelledError(f"Chat interrupted: {chat_id}")
