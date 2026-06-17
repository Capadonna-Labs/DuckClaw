"""Worker graph cache and per-vault invoke locks for the manager."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_worker_graph_cache: dict[str, Any] = {}
_vault_invoke_guard = threading.Lock()
_vault_invoke_locks: dict[str, threading.Lock] = {}


def worker_graph_cache_entry_count() -> int:
    """Cuántos grafos de worker hay en caché (tests / diagnóstico / comandos fly)."""
    return len(_worker_graph_cache)


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
    for _g in list(_worker_graph_cache.values()):
        wdb = getattr(_g, "_worker_db", None)
        if wdb is not None:
            try:
                wdb.close()
            except Exception:
                pass
    _worker_graph_cache.clear()


__all__ = [
    "_release_worker_db_handle",
    "_vault_invoke_guard",
    "_vault_invoke_locks",
    "_vault_lock_key",
    "_worker_graph_cache",
    "clear_worker_graph_cache",
    "worker_graph_cache_entry_count",
]
