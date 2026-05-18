"""
Identificación de subagentes (manager → worker).

- **Slot activo** (``acquire_subagent_slot``): sorted set en Redis con tokens en curso;
  el rank (1..n) es la etiqueta de UI/log: **subagent_slot_rank** entre ejecuciones
  **simultáneas** del mismo worker en el mismo ámbito. **No** es un índice de réplica PM2
  ni «Finanz 1 vs Finanz 2» como workers distintos: ``finanz 2`` solo indica que, al
  hacer ``ZADD``, este token quedó en segunda posición en el ZSET (p. ej. otra ejecución
  ``finanz`` del mismo chat aún no registró ``release``, o un token huérfano tras un fallo
  antes del ``finally``).

  **Comparar números entre workers no es significativo:** ``Job-Hunter 1`` y ``finanz 2``
  usan claves Redis distintas (el ``worker_id`` forma parte de la clave); cada uno cuenta
  solo sus propias ejecuciones concurrentes.

  Si solo hay una ejecución activa para ese worker/chat → rank 1.

  Con ``chat_id`` no vacío, el conjunto activo es por ``(tenant, worker, chat)``:
  dos usuarios distintos no comparten números. Sin ``chat_id`` (tests / legacy)
  el ámbito es solo ``(tenant, worker)``.

**Diagnóstico operativo (huérfanos / concurrencia):**

- Clave Redis (chat normalizado): ``duckclaw:subagent_active:{tenant}:{worker}:{chat}``
  (sin chat: ``duckclaw:subagent_active:{tenant}:{worker}``).
- ``ZCARD`` > 1 con una sola petición HTTP en curso sugiere tokens sin ``release`` o varias
  solicitudes solapadas al mismo worker/chat.

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
from typing import Any, Final

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


def _parse_active_redis_key(key: str, tenant_id: str) -> tuple[str, str | None] | None:
    """Devuelve (worker_id, chat_scope) desde clave Redis o None si no coincide."""
    prefix = f"{_REDIS_ACTIVE_PREFIX}{tenant_id}:"
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix) :]
    if not rest:
        return None
    parts = rest.split(":", 1)
    wid = parts[0].strip()
    if not wid:
        return None
    chat_scope = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return wid, chat_scope


def _slots_from_sorted_tokens(
    tokens: list[tuple[str, float]],
    worker_id: str,
    chat_scope: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rank, (token, score) in enumerate(tokens):
        out.append(
            {
                "worker_id": worker_id,
                "slot": rank + 1,
                "chat_scope": chat_scope,
                "token": token,
                "started_at": float(score),
                "active": True,
            }
        )
    return out


def _list_fallback_swarm_slots(
    tenant_id: str,
    worker_ids: list[str] | None,
) -> list[dict[str, Any]]:
    tid = str(tenant_id or "default").strip() or "default"
    allow = {w.strip() for w in (worker_ids or []) if w and w.strip()}
    rows: list[dict[str, Any]] = []
    with _fallback_lock:
        for fbk, tok_map in _fallback_active.items():
            if fbk[0] != tid:
                continue
            wid = fbk[1]
            if allow and wid not in allow:
                continue
            chat_scope = fbk[2] if len(fbk) > 2 else None
            sorted_toks = sorted(tok_map.items(), key=lambda x: x[1])
            rows.extend(_slots_from_sorted_tokens(sorted_toks, wid, chat_scope))
    return rows


def _dedupe_swarm_slots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Un slot por (worker_id, slot); prefiere fila con chat_scope definido."""
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        wid = str(row.get("worker_id") or "")
        slot = int(row.get("slot") or 0)
        if not wid or slot < 1:
            continue
        key = (wid, slot)
        prev = best.get(key)
        if prev is None:
            best[key] = row
            continue
        if prev.get("chat_scope") in (None, "") and row.get("chat_scope"):
            best[key] = row
    out = list(best.values())
    out.sort(key=lambda r: (str(r.get("worker_id") or ""), int(r.get("slot") or 0)))
    return out


def list_active_swarm_slots(
    tenant_id: str,
    worker_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Lista instancias swarm activas (slots 1..n) por worker desde Redis o fallback memoria.
    Cada fila: worker_id, slot, chat_scope, token, started_at, active.
    """
    tid = str(tenant_id or "default").strip() or "default"
    allow = [w.strip() for w in (worker_ids or []) if w and w.strip()]
    rows: list[dict[str, Any]] = []
    url = _redis_url()
    if url:
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            pattern = f"{_REDIS_ACTIVE_PREFIX}{tid}:*"
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor=cursor, match=pattern, count=100)
                for key in keys or []:
                    parsed = _parse_active_redis_key(key, tid)
                    if not parsed:
                        continue
                    wid, chat_scope = parsed
                    if allow and wid not in allow:
                        continue
                    members = client.zrange(key, 0, -1, withscores=True)
                    rows.extend(_slots_from_sorted_tokens(list(members), wid, chat_scope))
                if cursor == 0:
                    break
            return _dedupe_swarm_slots(rows)
        except Exception as exc:
            _log.debug("list_active_swarm_slots: Redis SCAN falló (%s), uso fallback", exc)
    rows = _list_fallback_swarm_slots(tid, allow or None)
    return _dedupe_swarm_slots(rows)


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
