"""Tests media_usage_log budget gate."""

from __future__ import annotations

import pytest

from duckclaw.media_usage_log import (
    MediaBudgetExceededError,
    assert_media_budget_ok,
    estimate_media_cost_usd,
    media_daily_budget_usd,
)


class _FakeDb:
    def __init__(self, total: float = 0.0):
        self._total = total
        self._read_only = False

    def execute(self, sql: str) -> None:
        pass

    def query(self, sql: str):
        import json
        return json.dumps([{"total": self._total}])


def test_estimate_flux_dev_cost() -> None:
    assert estimate_media_cost_usd("fal-ai/flux/dev", media_type="image") == 0.025


def test_estimate_video_cost_per_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_MEDIA_KLING_USD_PER_SEC", "0.07")
    assert estimate_media_cost_usd("fal-ai/kling-video/v1.6/standard/text-to-video", media_type="video", duration_sec=10) == 0.7


def test_budget_blocks_when_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_MEDIA_DAILY_BUDGET_USD", "5.0")
    db = _FakeDb(total=4.99)
    assert_media_budget_ok(db, "tenant-a", projected_cost_usd=0.005)
    with pytest.raises(MediaBudgetExceededError):
        assert_media_budget_ok(db, "tenant-a", projected_cost_usd=0.02)


def test_media_daily_budget_default() -> None:
    assert media_daily_budget_usd() == 2.0