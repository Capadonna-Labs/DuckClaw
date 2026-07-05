from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clear_worker_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED", "true")
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_MAX_ENTRIES", "2")
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_TTL_SEC", "600")
    from duckclaw.manager import manager_worker_cache as mwc

    mwc.clear_worker_graph_cache()


def test_worker_graph_cache_lru_evicts_oldest() -> None:
    from duckclaw.manager import manager_worker_cache as mwc

    g1 = MagicMock()
    g2 = MagicMock()
    g3 = MagicMock()
    mwc.remember_worker_graph_cache("k1", g1)
    mwc.remember_worker_graph_cache("k2", g2)
    mwc.remember_worker_graph_cache("k3", g3)
    assert mwc.worker_graph_cache_entry_count() == 2
    assert "k1" not in mwc._worker_graph_cache
    assert "k2" in mwc._worker_graph_cache
    assert "k3" in mwc._worker_graph_cache


def test_worker_graph_cache_get_drops_closed_db() -> None:
    from duckclaw.manager import manager_worker_cache as mwc

    graph = MagicMock()
    graph._worker_db = MagicMock(_con=None)
    mwc.remember_worker_graph_cache("k1", graph)
    assert mwc.worker_graph_cache_get("k1") is None
    assert mwc.worker_graph_cache_entry_count() == 0


def test_trim_force_clear() -> None:
    from duckclaw.manager import manager_worker_cache as mwc

    mwc.remember_worker_graph_cache("k1", MagicMock())
    mwc.trim_worker_graph_cache(force_clear=True)
    assert mwc.worker_graph_cache_entry_count() == 0


def test_gateway_health_metrics_shape() -> None:
    from duckclaw.ops.gateway_health_metrics import collect_gateway_health_metrics

    metrics = collect_gateway_health_metrics()
    assert "process_role" in metrics
    assert "worker_graph_cache" in metrics
    assert "knowledge_sync_queue_depth" in metrics
    assert "knowledge_embed_batch_size" in metrics
    assert "db_write_queue_depth" in metrics
    assert "rss_mb" in metrics
