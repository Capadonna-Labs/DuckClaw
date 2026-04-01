"""
Human-in-the-loop para execute_order: grant vía /execute_signal <uuid>.

Usa Redis si REDIS_URL o DUCKCLAW_REDIS_URL está definido; si no, memoria en proceso
(solo válido si gateway y tools comparten el mismo proceso).
"""

from __future__ import annotations

import logging
import os
import threading
import time
_log = logging.getLogger(__name__)

_TTL_SEC = 600
_memory_grants: dict[tuple[str, str], float] = {}
_memory_lock = threading.Lock()


def _redis_client():
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        _log.warning("[quant_hitl] redis unavailable: %s", e)
        return None


def _key(chat_id: str, signal_id: str) -> str:
    return f"duckclaw:quant_exec:{chat_id}:{signal_id}"


def grant_execute_order(chat_id: str, signal_id: str) -> None:
    """Marca que un único execute_order está autorizado para este par chat+señal."""
    cid = (chat_id or "").strip()
    sid = (signal_id or "").strip().lower()
    if not cid or not sid:
        return
    r = _redis_client()
    if r is not None:
        try:
            r.setex(_key(cid, sid), _TTL_SEC, "1")
            return
        except Exception as e:
            _log.warning("[quant_hitl] redis setex failed: %s", e)
    with _memory_lock:
        _memory_grants[(cid, sid)] = time.time() + _TTL_SEC


def consume_execute_order_grant(chat_id: str, signal_id: str) -> bool:
    """True si había grant válido y se consume (una sola vez)."""
    cid = (chat_id or "").strip()
    sid = (signal_id or "").strip().lower()
    if not cid or not sid:
        return False
    r = _redis_client()
    if r is not None:
        try:
            k = _key(cid, sid)
            val = r.get(k)
            if val == "1" or val == 1:
                r.delete(k)
                return True
            return False
        except Exception as e:
            _log.warning("[quant_hitl] redis consume failed: %s", e)
            return False
    now = time.time()
    with _memory_lock:
        exp = _memory_grants.pop((cid, sid), None)
        return exp is not None and exp > now


def clear_grant(chat_id: str, signal_id: str) -> None:
    """Limpia grant sin consumir (tests / admin)."""
    cid = (chat_id or "").strip()
    sid = (signal_id or "").strip().lower()
    r = _redis_client()
    if r is not None:
        try:
            r.delete(_key(cid, sid))
        except Exception:
            pass
    with _memory_lock:
        _memory_grants.pop((cid, sid), None)
