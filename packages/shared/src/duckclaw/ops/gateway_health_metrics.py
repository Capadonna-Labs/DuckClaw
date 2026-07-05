"""Lightweight metrics for Gateway /health (no blocking I/O beyond Redis LLEN)."""

from __future__ import annotations

import resource
import sys
import time
from typing import Any


def _process_rss_mb() -> float | None:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            return round(rss / (1024 * 1024), 1)
        return round(rss / 1024, 1)
    except Exception:
        return None


def _worker_graph_cache_stats() -> dict[str, Any]:
    try:
        from duckclaw.manager.manager_worker_cache import worker_graph_cache_stats

        return worker_graph_cache_stats()
    except Exception:
        return {"enabled": False, "entries": 0}


def _knowledge_queue_depth() -> int | None:
    try:
        import redis

        from duckclaw.knowledge_sync_queue import KNOWLEDGE_SYNC_QUEUE_KEY
        from duckclaw.runtime_env import resolve_redis_url

        client = redis.from_url(resolve_redis_url(), decode_responses=True)
        return int(client.llen(KNOWLEDGE_SYNC_QUEUE_KEY))
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
    return {
        "process_role": role,
        "rss_mb": _process_rss_mb(),
        "worker_graph_cache": cache,
        "knowledge_sync_queue_depth": _knowledge_queue_depth(),
        "collected_at": round(time.time(), 3),
    }
