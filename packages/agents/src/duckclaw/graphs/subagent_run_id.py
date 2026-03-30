"""
Identificación de subagentes (manager → worker).

- **Slot activo** (``acquire_subagent_slot``): sorted set en Redis con tokens en curso;
  el rank (1..n) es la etiqueta de UI: número de instancia entre ejecuciones **simultáneas**
  del mismo worker. Si solo hay una activa → 1; al liberar slots, las que siguen
  ocupan el rango según los que queden en curso (otra vez 1 si eres el único).

  Con ``chat_id`` no vacío, el conjunto activo es por ``(tenant, worker, chat)``:
  dos usuarios distintos no comparten números. Sin ``chat_id`` (tests / legacy)
  el ámbito es solo ``(tenant, worker)``.

Redis:
- ``duckclaw:subagent_active:{tenant}:{worker}`` — ZSET (sin chat)
- ``duckclaw:subagent_active:{tenant}:{worker}:{chat}`` — ZSET (con chat normalizado)
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Final

_log = logging.getLogger(__name__)

_REDIS_ACTIVE_PREFIX: Final[str] = "duckclaw:subagent_active:"

_fallback_lock = threading.Lock()
# (tid, wid) o (tid, wid, chat_scope) -> {token: monotonic_ts}
_fallback_active: dict[tuple[str, ...], dict[str, float]] = {}


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()


def _norm_ids(tenant_id: str, worker_id: str) -> tuple[str, str]:
    tid = str(tenant_id or "default").strip() or "default"
    wid = str(worker_id or "").strip() or "worker"
    return tid, wid


def _norm_chat_scope(chat_id: str | None) -> str | None:
    raw = str(chat_id or "").strip()
    if not raw:
        return None
    from duckclaw.graphs.chat_heartbeat import normalize_telegram_chat_id_for_outbound

    return normalize_telegram_chat_id_for_outbound(raw) or raw


def _active_key(tid: str, wid: str, chat_scope: str | None) -> str:
    base = f"{_REDIS_ACTIVE_PREFIX}{tid}:{wid}"
    if chat_scope is None:
        return base
    return f"{base}:{chat_scope}"


def _fallback_bucket_key(tid: str, wid: str, chat_scope: str | None) -> tuple[str, ...]:
    if chat_scope is None:
        return (tid, wid)
    return (tid, wid, chat_scope)


def acquire_subagent_slot(
    tenant_id: str,
    worker_id: str,
    chat_id: str | None = None,
) -> tuple[str, int]:
    """
    Registra una ejecución en curso. Devuelve (token_opaco, etiqueta 1..n entre activas).
    Llamar a ``release_subagent_slot`` en ``finally`` con el mismo ``chat_id``.
    """
    tid, wid = _norm_ids(tenant_id, worker_id)
    cscope = _norm_chat_scope(chat_id)
    token = str(uuid.uuid4())
    url = _redis_url()
    if url:
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            key = _active_key(tid, wid, cscope)
            client.zadd(key, {token: time.time()})
            rank = client.zrank(key, token)
            return token, int(rank) + 1 if rank is not None else 1
        except Exception as exc:
            _log.debug("subagent_run_id: Redis ZADD falló (%s), uso fallback en memoria", exc)
    fbk = _fallback_bucket_key(tid, wid, cscope)
    with _fallback_lock:
        d = _fallback_active.setdefault(fbk, {})
        d[token] = time.monotonic()
        sorted_toks = sorted(d.keys(), key=lambda t: d[t])
        rank = sorted_toks.index(token)
        return token, rank + 1


def release_subagent_slot(
    tenant_id: str,
    worker_id: str,
    token: str,
    chat_id: str | None = None,
) -> None:
    """Quita la ejecución del conjunto activo."""
    if not token:
        return
    tid, wid = _norm_ids(tenant_id, worker_id)
    cscope = _norm_chat_scope(chat_id)
    url = _redis_url()
    if url:
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            key = _active_key(tid, wid, cscope)
            client.zrem(key, token)
            if int(client.zcard(key) or 0) == 0:
                client.delete(key)
            return
        except Exception as exc:
            _log.debug("subagent_run_id: Redis ZREM falló (%s), uso fallback en memoria", exc)
    fbk = _fallback_bucket_key(tid, wid, cscope)
    with _fallback_lock:
        d = _fallback_active.get(fbk)
        if not d:
            return
        d.pop(token, None)
        if not d:
            _fallback_active.pop(fbk, None)


def active_subagent_label(
    tenant_id: str,
    worker_id: str,
    token: str,
    chat_id: str | None = None,
) -> int:
    """
    Etiqueta actual (1 + orden entre activas) del token mientras siga registrado.
    Si el token no está (p. ej. ya liberado), devuelve 1.
    """
    if not token:
        return 1
    tid, wid = _norm_ids(tenant_id, worker_id)
    cscope = _norm_chat_scope(chat_id)
    url = _redis_url()
    if url:
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            key = _active_key(tid, wid, cscope)
            rank = client.zrank(key, token)
            return int(rank) + 1 if rank is not None else 1
        except Exception as exc:
            _log.debug("subagent_run_id: Redis ZRANK falló (%s), uso fallback en memoria", exc)
    fbk = _fallback_bucket_key(tid, wid, cscope)
    with _fallback_lock:
        d = _fallback_active.get(fbk, {})
        if token not in d:
            return 1
        sorted_toks = sorted(d.keys(), key=lambda t: d[t])
        return sorted_toks.index(token) + 1
