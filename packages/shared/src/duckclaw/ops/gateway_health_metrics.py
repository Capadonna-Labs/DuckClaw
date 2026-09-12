"""Lightweight metrics for Gateway /health (no blocking I/O beyond Redis LLEN)."""

from __future__ import annotations

import sys
import time
from typing import Any

PM2_METRICS_CACHE_SEC = 30
_pm2_metrics_cache: dict[str, Any] = {"expires_at": 0.0, "rows": []}

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]


def _process_rss_mb() -> float | None:
    if resource is None:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            return round(rss / (1024 * 1024), 1)
        return round(rss / 1024, 1)
    except Exception:
        return None


def process_rss_mb() -> float | None:
    """RSS del proceso Gateway (pico vía ``getrusage``)."""
    return _process_rss_mb()


def _worker_graph_cache_stats() -> dict[str, Any]:
    try:
        from duckclaw.manager.manager_worker_cache import worker_graph_cache_stats

        return worker_graph_cache_stats()
    except Exception:
        return {"enabled": False, "entries": 0}


def _worker_capabilities_catalog_cache_stats() -> dict[str, Any]:
    try:
        from duckclaw.ops.worker_capabilities_catalog_cache import (
            worker_capabilities_catalog_cache_stats,
        )

        return worker_capabilities_catalog_cache_stats()
    except Exception:
        return {"enabled": False, "entries": 0}


def _knowledge_queue_depth() -> int | None:
    try:
        from duckclaw.spawn_profile import is_lite_mode

        # Desktop Lite has no Knowledge-Indexer / Redis — same reasoning as
        # _db_write_queue_depth above.
        if is_lite_mode():
            return None

        from duckclaw.knowledge_sync_queue import knowledge_sync_queue_depth

        return knowledge_sync_queue_depth()
    except Exception:
        return None


def _cached_pm2_stack_health() -> list[dict[str, Any]]:
    now = time.time()
    if now < float(_pm2_metrics_cache["expires_at"]):
        rows = _pm2_metrics_cache["rows"]
        return rows if isinstance(rows, list) else []
    try:
        from duckclaw.spawn_profile import is_lite_mode

        # Desktop Lite never runs PM2 — resolving the pm2 executable to then get an
        # empty/N-A result can itself take several seconds on some hosts (PATH/npm
        # global lookup), which is wasted time on this /health hot path every time the
        # 30s cache expires. Same reasoning as the Redis skips above.
        if is_lite_mode():
            rows = []
        else:
            from duckclaw.ops.pm2_stack_health import collect_pm2_stack_health

            rows = collect_pm2_stack_health()
    except Exception:
        rows = []
    _pm2_metrics_cache["expires_at"] = now + PM2_METRICS_CACHE_SEC
    _pm2_metrics_cache["rows"] = rows
    return rows


def _db_write_queue_depth() -> int | None:
    try:
        from duckclaw.spawn_profile import is_lite_mode

        # Desktop Lite has no Redis/db-writer at all (inline writes) — skip the probe
        # entirely instead of risking a hung connect (see socket_connect_timeout below
        # for the non-lite case: a refused connection fails fast, but on some hosts an
        # unreachable/firewalled Redis just hangs the TCP handshake indefinitely, and
        # this runs inside /health's asyncio.to_thread — a stuck call there starves the
        # thread pool for every other request until the connect finally gives up).
        if is_lite_mode():
            return None

        import redis

        from duckclaw.db_write_queue import DEFAULT_WRITE_QUEUE_NAME
        from duckclaw.runtime_env import resolve_redis_url

        client = redis.from_url(
            resolve_redis_url(),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        return int(client.llen(DEFAULT_WRITE_QUEUE_NAME))
    except Exception:
        return None


def collect_gateway_health_metrics() -> dict[str, Any]:
    role = "unknown"
    try:
        from duckclaw.process_role import process_role

        role = process_role()
    except Exception:
        pass

    cache = _worker_graph_cache_stats()
    caps_cache = _worker_capabilities_catalog_cache_stats()
    pm2_processes = _cached_pm2_stack_health()

    embed_batch_size: int | None = None
    try:
        from duckclaw.knowledge_indexer_config import knowledge_embed_batch_size

        embed_batch_size = knowledge_embed_batch_size()
    except Exception:
        pass

    return {
        "process_role": role,
        "rss_mb": _process_rss_mb(),
        "worker_graph_cache": cache,
        "worker_capabilities_catalog_cache": caps_cache,
        "knowledge_sync_queue_depth": _knowledge_queue_depth(),
        "knowledge_embed_batch_size": embed_batch_size,
        "db_write_queue_depth": _db_write_queue_depth(),
        "pm2_processes": pm2_processes,
        "collected_at": round(time.time(), 3),
    }
