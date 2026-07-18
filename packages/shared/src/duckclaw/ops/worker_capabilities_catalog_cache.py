"""In-process LRU+TTL cache for admin worker capabilities catalog payloads.

Mirrors ``manager_worker_cache`` policy: Gateway process memory, explicit
invalidation on catalog writes and ``release-worker-cache``. Not a UI cache.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from collections import OrderedDict
from typing import Any

_lock = threading.RLock()
_catalog_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()


def worker_capabilities_catalog_cache_enabled() -> bool:
    raw = (os.environ.get("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_ENABLED") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def worker_capabilities_catalog_cache_max_entries() -> int:
    try:
        return max(1, min(int(os.environ.get("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_MAX_ENTRIES") or "64"), 256))
    except ValueError:
        return 64


def worker_capabilities_catalog_cache_ttl_sec() -> float:
    try:
        return max(15.0, float(os.environ.get("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_TTL_SEC") or "120"))
    except ValueError:
        return 120.0


def worker_capabilities_catalog_cache_entry_count() -> int:
    with _lock:
        return len(_catalog_cache)


def worker_capabilities_catalog_cache_stats() -> dict[str, Any]:
    return {
        "enabled": worker_capabilities_catalog_cache_enabled(),
        "entries": worker_capabilities_catalog_cache_entry_count(),
        "max_entries": worker_capabilities_catalog_cache_max_entries(),
        "ttl_sec": worker_capabilities_catalog_cache_ttl_sec(),
    }


def capabilities_catalog_cache_key(worker_id: str, *, actor: str = "admin-ui") -> str:
    wid = (worker_id or "").strip().lower()
    act = (actor or "admin-ui").strip().lower() or "admin-ui"
    return f"{act}:{wid}"


def clear_worker_capabilities_catalog_cache() -> None:
    with _lock:
        _catalog_cache.clear()


def invalidate_worker_capabilities_catalog(worker_id: str) -> int:
    """Drop all entries for ``worker_id`` (any actor). Returns removed count."""
    wid = (worker_id or "").strip().lower()
    if not wid:
        return 0
    suffix = f":{wid}"
    removed = 0
    with _lock:
        for key in list(_catalog_cache.keys()):
            if key.endswith(suffix) or key == wid:
                _catalog_cache.pop(key, None)
                removed += 1
    return removed


def _evict_expired_locked(now: float) -> None:
    ttl = worker_capabilities_catalog_cache_ttl_sec()
    for key in list(_catalog_cache.keys()):
        entry = _catalog_cache.get(key)
        if entry is None:
            continue
        stored_at = float(entry.get("stored_at") or 0.0)
        if now - stored_at > ttl:
            _catalog_cache.pop(key, None)


def _trim_lru_locked() -> None:
    max_entries = worker_capabilities_catalog_cache_max_entries()
    while len(_catalog_cache) > max_entries:
        oldest = next(iter(_catalog_cache), None)
        if oldest is None:
            break
        _catalog_cache.pop(oldest, None)


def get_cached_worker_capabilities(cache_key: str) -> dict[str, Any] | None:
    if not worker_capabilities_catalog_cache_enabled():
        return None
    now = time.monotonic()
    with _lock:
        _evict_expired_locked(now)
        entry = _catalog_cache.get(cache_key)
        if entry is None:
            return None
        stored_at = float(entry.get("stored_at") or 0.0)
        if now - stored_at > worker_capabilities_catalog_cache_ttl_sec():
            _catalog_cache.pop(cache_key, None)
            return None
        _catalog_cache.move_to_end(cache_key)
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            _catalog_cache.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)


def remember_worker_capabilities(cache_key: str, payload: dict[str, Any]) -> None:
    if not worker_capabilities_catalog_cache_enabled():
        return
    if not cache_key or not isinstance(payload, dict):
        return
    with _lock:
        _catalog_cache[cache_key] = {
            "payload": copy.deepcopy(payload),
            "stored_at": time.monotonic(),
        }
        _catalog_cache.move_to_end(cache_key)
        _trim_lru_locked()
