from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_worker_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_WORKER_GRAPH_CACHE_ENABLED", "true")
    from duckclaw.manager import manager_worker_cache as mwc

    mwc.clear_worker_graph_cache()


def test_release_worker_graph_cache_clears_entries() -> None:
    from duckclaw.manager import manager_worker_cache as mwc
    from duckclaw.ops.gateway_resource_release import release_worker_graph_cache

    mwc.remember_worker_graph_cache("k1", MagicMock())
    mwc.remember_worker_graph_cache("k2", MagicMock())
    assert mwc.worker_graph_cache_entry_count() == 2

    with patch("duckclaw.ops.gateway_resource_release.gc.collect"):
        result = release_worker_graph_cache(force=True)

    assert result["ok"] is True
    assert result["entries_before"] == 2
    assert result["entries_after"] == 0
    assert mwc.worker_graph_cache_entry_count() == 0


def test_release_worker_graph_cache_idempotent_when_empty() -> None:
    from duckclaw.ops.gateway_resource_release import release_worker_graph_cache

    with patch("duckclaw.ops.gateway_resource_release.gc.collect"):
        result = release_worker_graph_cache(force=True)

    assert result["entries_before"] == 0
    assert result["entries_after"] == 0
