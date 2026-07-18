"""Tests for in-process worker capabilities catalog cache."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_caps_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_ENABLED", "true")
    monkeypatch.setenv("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_MAX_ENTRIES", "2")
    monkeypatch.setenv("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_TTL_SEC", "600")
    from duckclaw.ops import worker_capabilities_catalog_cache as caps

    caps.clear_worker_capabilities_catalog_cache()


def test_capabilities_catalog_cache_hit_and_deepcopy() -> None:
    from duckclaw.ops import worker_capabilities_catalog_cache as caps

    key = caps.capabilities_catalog_cache_key("default", actor="admin@x")
    payload = {"worker_id": "default", "gaps": ["a"]}
    caps.remember_worker_capabilities(key, payload)
    hit = caps.get_cached_worker_capabilities(key)
    assert hit == payload
    assert hit is not payload
    hit["gaps"].append("mutated")
    again = caps.get_cached_worker_capabilities(key)
    assert again == {"worker_id": "default", "gaps": ["a"]}


def test_capabilities_catalog_cache_lru_evicts() -> None:
    from duckclaw.ops import worker_capabilities_catalog_cache as caps

    caps.remember_worker_capabilities("a:w1", {"worker_id": "w1"})
    caps.remember_worker_capabilities("a:w2", {"worker_id": "w2"})
    caps.remember_worker_capabilities("a:w3", {"worker_id": "w3"})
    assert caps.worker_capabilities_catalog_cache_entry_count() == 2
    assert caps.get_cached_worker_capabilities("a:w1") is None
    assert caps.get_cached_worker_capabilities("a:w2") is not None
    assert caps.get_cached_worker_capabilities("a:w3") is not None


def test_invalidate_worker_drops_all_actors(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.ops import worker_capabilities_catalog_cache as caps

    monkeypatch.setenv("DUCKCLAW_WORKER_CAPABILITIES_CATALOG_CACHE_MAX_ENTRIES", "8")
    caps.clear_worker_capabilities_catalog_cache()
    caps.remember_worker_capabilities("actor1:demo", {"worker_id": "demo"})
    caps.remember_worker_capabilities("actor2:demo", {"worker_id": "demo"})
    caps.remember_worker_capabilities("actor1:other", {"worker_id": "other"})
    removed = caps.invalidate_worker_capabilities_catalog("demo")
    assert removed == 2
    assert caps.get_cached_worker_capabilities("actor1:demo") is None
    assert caps.get_cached_worker_capabilities("actor2:demo") is None
    assert caps.get_cached_worker_capabilities("actor1:other") is not None


def test_release_worker_cache_clears_capabilities_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.manager import manager_worker_cache as mwc
    from duckclaw.ops import worker_capabilities_catalog_cache as caps
    from duckclaw.ops.gateway_resource_release import release_worker_graph_cache

    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED", "true")
    mwc.clear_worker_graph_cache()
    caps.remember_worker_capabilities("a:w1", {"worker_id": "w1"})
    assert caps.worker_capabilities_catalog_cache_entry_count() == 1

    result = release_worker_graph_cache(force=True)
    assert result["ok"] is True
    assert result["capabilities_catalog_entries_before"] == 1
    assert result["capabilities_catalog_entries_after"] == 0
    assert result["worker_capabilities_catalog_cache"]["entries"] == 0
    assert caps.worker_capabilities_catalog_cache_entry_count() == 0


def test_gateway_health_includes_capabilities_catalog_cache() -> None:
    from duckclaw.ops.gateway_health_metrics import collect_gateway_health_metrics

    metrics = collect_gateway_health_metrics()
    assert "worker_capabilities_catalog_cache" in metrics
    assert "enabled" in metrics["worker_capabilities_catalog_cache"]
