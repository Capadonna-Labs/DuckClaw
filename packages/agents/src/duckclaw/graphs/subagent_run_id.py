"""
Secuencia incremental por (tenant, worker) para identificar instancias de subagentes (swarms).

Clave Redis: duckclaw:subagent_run_seq:{tenant_id}:{worker_id} — INCR atómico.
Sin Redis: contador en memoria por proceso (no apto multi-instancia).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Final

_log = logging.getLogger(__name__)

_REDIS_KEY_PREFIX: Final[str] = "duckclaw:subagent_run_seq:"

_fallback_lock = threading.Lock()
_fallback: dict[tuple[str, str], int] = {}


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()


def next_subagent_run_number(tenant_id: str, worker_id: str) -> int:
    """
    Siguiente número de ejecución para este subagente (1, 2, 3, …).
    Aislamiento por tenant y por id de plantilla (p. ej. SIATA-Analyst).
    """
    tid = str(tenant_id or "default").strip() or "default"
    wid = str(worker_id or "").strip() or "worker"
    url = _redis_url()
    if url:
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            key = f"{_REDIS_KEY_PREFIX}{tid}:{wid}"
            return int(client.incr(key))
        except Exception as exc:
            _log.debug("subagent_run_id: Redis INCR falló (%s), uso fallback en memoria", exc)
    with _fallback_lock:
        k = (tid, wid)
        n = _fallback.get(k, 0) + 1
        _fallback[k] = n
        return n
