"""
ActivityManager — estado de tareas por chat/sesión (IDLE, BUSY).

Usa Redis para persistir estado. El Gateway marca BUSY al iniciar una invocación
y IDLE al terminar. /tasks consulta este estado.

Env: DUCKCLAW_WRITE_QUEUE_URL o DUCKCLAW_REDIS_URL (redis://localhost/0)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

_ACTIVITY_KEY_PREFIX = "duckclaw:activity:"
_REDIS_URL_ENV = "DUCKCLAW_REDIS_URL"
_QUEUE_URL_ENV = "DUCKCLAW_WRITE_QUEUE_URL"


def _get_redis_url() -> Optional[str]:
    url = os.environ.get(_REDIS_URL_ENV, "").strip() or os.environ.get(_QUEUE_URL_ENV, "").strip()
    return url or None


def _activity_key(chat_id: Any) -> str:
    return f"{_ACTIVITY_KEY_PREFIX}{chat_id}"


def set_busy(chat_id: Any, task: str = "", worker_id: Optional[str] = None) -> None:
    """Marca el chat como BUSY con la tarea actual y opcionalmente el worker/subagente."""
    url = _get_redis_url()
    if not url:
        return
    try:
        import redis
        r = redis.from_url(url)
        data: Dict[str, Any] = {
            "status": "BUSY",
            "task": (task or "")[:256],
            "started_at": int(time.time()),
        }
        if worker_id and str(worker_id).strip():
            data["worker_id"] = str(worker_id).strip()[:64]
        payload = json.dumps(data)
        r.setex(_activity_key(chat_id), 3600, payload)  # TTL 1h
    except Exception:
        pass


def set_idle(chat_id: Any) -> None:
    """Marca el chat como IDLE."""
    url = _get_redis_url()
    if not url:
        return
    try:
        import redis
        r = redis.from_url(url)
        r.delete(_activity_key(chat_id))
    except Exception:
        pass


def get_activity(chat_id: Any) -> Optional[Dict[str, Any]]:
    """
    Obtiene el estado de actividad del chat.
    Retorna None si no hay Redis o no hay dato (IDLE implícito).
    Incluye worker_id si fue pasado a set_busy (subagente ejecutando la tarea).
    """
    url = _get_redis_url()
    if not url:
        return None
    try:
        import redis
        r = redis.from_url(url)
        raw = r.get(_activity_key(chat_id))
        if raw:
            data = json.loads(raw)
            if isinstance(data, dict) and "worker_id" not in data:
                data["worker_id"] = ""
            return data
        return {"status": "IDLE", "task": "", "started_at": 0, "worker_id": ""}
    except Exception:
        return None
