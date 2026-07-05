"""Gateway in-process resource release (admin UI, fly commands)."""

from __future__ import annotations

import gc
from typing import Any


def release_worker_graph_cache(*, force: bool = True) -> dict[str, Any]:
    """
    Vacía la caché LRU de grafos LangGraph y fuerza ``gc.collect()``.

    Retorna contadores before/after para auditoría y UI. ``rss_mb_*`` usa
    ``getrusage(RUSAGE_SELF).ru_maxrss`` (pico del proceso, no RSS instantáneo).
    """
    from duckclaw.manager.manager_worker_cache import (
        trim_worker_graph_cache,
        worker_graph_cache_entry_count,
        worker_graph_cache_stats,
    )
    from duckclaw.ops.gateway_health_metrics import process_rss_mb

    entries_before = worker_graph_cache_entry_count()
    rss_before = process_rss_mb()

    trim_worker_graph_cache(force_clear=force)
    gc.collect()

    entries_after = worker_graph_cache_entry_count()
    rss_after = process_rss_mb()

    return {
        "ok": True,
        "entries_before": entries_before,
        "entries_after": entries_after,
        "rss_mb_before": rss_before,
        "rss_mb_after": rss_after,
        "worker_graph_cache": worker_graph_cache_stats(),
    }
