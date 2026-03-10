"""
SessionStateManager — estado por thread_id para HITL Handoff.

Spec: specs/Protocolo_Escalamiento_Humano_HITL_Handoff.md

Estados: IDLE, BUSY, HANDOFF_REQUESTED, MANUAL_MODE
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

SESSION_PREFIX = "duckclaw:session_state:"
STATE_IDLE = "IDLE"
STATE_BUSY = "BUSY"
STATE_HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
STATE_MANUAL_MODE = "MANUAL_MODE"


def _get_redis_url() -> str:
    return os.environ.get("REDIS_URL") or os.environ.get("ARQ_REDIS_URL") or "redis://localhost:6379"


class SessionStateManager:
    """Gestiona estado de sesión por thread_id en Redis (HITL Handoff)."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = (redis_url or _get_redis_url()).strip()
        self._redis: Any = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            try:
                import redis
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
            except ImportError:
                raise RuntimeError("redis no instalado. Ejecuta: uv sync --extra queue")
        return self._redis

    def _key(self, thread_id: str) -> str:
        return f"{SESSION_PREFIX}{thread_id}"

    def get_status(self, thread_id: str) -> str:
        """Estado actual. Default IDLE si no hay Redis o clave."""
        try:
            r = self._get_redis()
            s = r.hget(self._key(thread_id), "status")
            return (s or STATE_IDLE).upper()
        except Exception:
            return STATE_IDLE

    def set_status(self, thread_id: str, status: str, context_summary: str = "") -> None:
        """Establece estado y opcionalmente context_summary."""
        try:
            r = self._get_redis()
            key = self._key(thread_id)
            r.hset(key, mapping={"status": status, "context_summary": context_summary, "updated_at": str(time.time())})
            r.expire(key, 86400 * 7)  # 7 días TTL
        except Exception:
            pass

    def request_handoff(self, thread_id: str, reason: str, context_summary: str) -> None:
        """Transición a HANDOFF_REQUESTED."""
        self.set_status(thread_id, STATE_HANDOFF_REQUESTED, f"{reason}: {context_summary}")

    def takeover(self, thread_id: str) -> None:
        """Humano asume control → MANUAL_MODE."""
        self.set_status(thread_id, STATE_MANUAL_MODE)

    def release(self, thread_id: str) -> None:
        """Humano libera → IDLE."""
        self.set_status(thread_id, STATE_IDLE)

    def get_context(self, thread_id: str) -> str:
        """Obtiene context_summary guardado."""
        try:
            r = self._get_redis()
            return r.hget(self._key(thread_id), "context_summary") or ""
        except Exception:
            return ""
