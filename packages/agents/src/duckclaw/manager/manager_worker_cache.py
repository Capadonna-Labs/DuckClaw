"""Worker graph cache and per-vault invoke locks for the manager."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

_worker_graph_cache: OrderedDict[str, Any] = OrderedDict()
_vault_invoke_guard = threading.Lock()
_vault_invoke_locks: dict[str, threading.Lock] = {}


def worker_graph_cache_enabled() -> bool:
    raw = (os.environ.get("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def worker_graph_cache_max_entries() -> int:
    try:
        return max(1, min(int(os.environ.get("DUCKCLAW_WORKER_GRAPH_CACHE_MAX_ENTRIES") or "8"), 64))
    except ValueError:
        return 8


def worker_graph_cache_ttl_sec() -> float:
    try:
        return max(30.0, float(os.environ.get("DUCKCLAW_WORKER_GRAPH_CACHE_TTL_SEC") or "600"))
    except ValueError:
        return 600.0


def worker_graph_cache_entry_count() -> int:
    """Cuántos grafos de worker hay en caché (tests / diagnóstico / comandos fly)."""
    return len(_worker_graph_cache)


def worker_graph_cache_stats() -> dict[str, Any]:
    return {
        "enabled": worker_graph_cache_enabled(),
        "entries": worker_graph_cache_entry_count(),
        "max_entries": worker_graph_cache_max_entries(),
        "ttl_sec": worker_graph_cache_ttl_sec(),
    }


def touch_worker_graph_cache(cache_key: str) -> None:
    if cache_key not in _worker_graph_cache:
        return
    _worker_graph_cache.move_to_end(cache_key)
    setattr(_worker_graph_cache[cache_key], "_cache_last_used", time.monotonic())


def _close_graph_worker_db(graph: Any | None) -> None:
    if graph is None:
        return
    wdb = getattr(graph, "_worker_db", None)
    if wdb is None:
        return
    try:
        wdb.close()
    except Exception:
        pass
    try:
        graph._worker_db = None
    except Exception:
        pass


def _evict_cache_key(cache_key: str) -> None:
    graph = _worker_graph_cache.pop(cache_key, None)
    _close_graph_worker_db(graph)


def trim_worker_graph_cache(*, force_clear: bool = False) -> None:
    """
    Cierra handles DuckDB en entradas retenidas y aplica TTL + LRU.
    ``force_clear`` vacía todo (fly commands, tests).
    """
    if force_clear or not worker_graph_cache_enabled():
        clear_worker_graph_cache()
        return

    now = time.monotonic()
    ttl = worker_graph_cache_ttl_sec()
    for key in list(_worker_graph_cache.keys()):
        graph = _worker_graph_cache.get(key)
        last_used = getattr(graph, "_cache_last_used", now)
        if now - float(last_used) > ttl:
            _evict_cache_key(key)
        else:
            _close_graph_worker_db(graph)

    max_entries = worker_graph_cache_max_entries()
    while len(_worker_graph_cache) > max_entries:
        oldest_key = next(iter(_worker_graph_cache), None)
        if oldest_key is None:
            break
        _evict_cache_key(oldest_key)


def remember_worker_graph_cache(cache_key: str, graph: Any) -> None:
    setattr(graph, "_cache_last_used", time.monotonic())
    _worker_graph_cache[cache_key] = graph
    _worker_graph_cache.move_to_end(cache_key)
    max_entries = worker_graph_cache_max_entries()
    while len(_worker_graph_cache) > max_entries:
        oldest_key = next(iter(_worker_graph_cache), None)
        if oldest_key is None or oldest_key == cache_key:
            break
        _evict_cache_key(oldest_key)


def worker_graph_cache_get(cache_key: str) -> Any | None:
    graph = _worker_graph_cache.get(cache_key)
    if graph is None:
        return None
    wdb = getattr(graph, "_worker_db", None)
    if wdb is not None and getattr(wdb, "_con", None) is not None:
        touch_worker_graph_cache(cache_key)
        setattr(graph, "_cache_last_used", time.monotonic())
        return graph
    _evict_cache_key(cache_key)
    return None


def _vault_lock_key(path: str) -> str:
    p = (path or "").strip()
    if not p or p == ":memory:":
        return ""
    try:
        return str(Path(p).expanduser().resolve())
    except Exception:
        return str(Path(p).expanduser())


def _release_worker_db_handle(worker_graph: Any | None, *, cache_key: str = "") -> bool:
    """
    Cierra ``_worker_db`` del grafo cacheado y opcionalmente lo saca de la caché.

    Debe llamarse en cuanto termina ``worker_graph.invoke`` si el worker abrió RW en el
    mismo .duckdb que el manager y usa herramientas RW: dejar el handle abierto hasta el
    ``finally`` del nodo bloquea db-writer y provoca «different configuration» al reabrir RO.
    """
    if worker_graph is None:
        return False
    wdb = getattr(worker_graph, "_worker_db", None)
    if wdb is None:
        return False
    try:
        wdb.close()
    except Exception:
        pass
    try:
        worker_graph._worker_db = None
    except Exception:
        pass
    if cache_key and worker_graph_cache_enabled():
        setattr(worker_graph, "_cache_last_used", time.monotonic())
        return True
    if cache_key:
        try:
            _worker_graph_cache.pop(cache_key, None)
        except Exception:
            pass
    return True


def clear_worker_graph_cache() -> None:
    """
    Los grafos de worker cierran sobre un DuckClaw concreto; tras cerrar la conexión del manager
    hay que vaciar la caché para no reutilizar handles muertos en la siguiente petición.

    Cierra explícitamente ``_worker_db`` en cada grafo cacheado antes de vaciar: DuckDB no permite
    dos conexiones al mismo archivo con configuración distinta (p. ej. RW del worker + nuevo RW
    para /model, /team en fly).
    """
    for key in list(_worker_graph_cache.keys()):
        _evict_cache_key(key)


__all__ = [
    "_release_worker_db_handle",
    "_vault_invoke_guard",
    "_vault_invoke_locks",
    "_vault_lock_key",
    "_worker_graph_cache",
    "clear_worker_graph_cache",
    "remember_worker_graph_cache",
    "trim_worker_graph_cache",
    "worker_graph_cache_enabled",
    "worker_graph_cache_entry_count",
    "worker_graph_cache_get",
    "worker_graph_cache_stats",
]
