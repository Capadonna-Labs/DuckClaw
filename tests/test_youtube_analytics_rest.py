"""Tests for the YouTube Analytics REST skill bridge (no Google-hosted MCP for these APIs)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from duckclaw.forge.skills.youtube_analytics_rest import (
    call_youtube_analytics_rest,
    uses_youtube_analytics_rest_fallback,
    youtube_analytics_rest_fallback_tool_specs,
)


class _FakeResp:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._payload


def test_missing_bearer_token_returns_error_without_http_call() -> None:
    out = asyncio.run(call_youtube_analytics_rest("get_video_public_info", {"video_id": "abc"}, headers=None))
    assert "missing bearer token" in out


def test_unsupported_tool_returns_error() -> None:
    async def fake_get(self, url, params=None):
        raise AssertionError("should not call HTTP for an unsupported tool")

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_analytics_rest(
                "not_a_real_tool", {}, headers={"Authorization": "Bearer tok"}
            )
        )
    assert "unsupported tool" in out


def test_get_video_analytics_passes_video_filter_and_returns_json() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp(payload={"rows": [[100, 50.0, 30.0, 10, 5.0, 2, 1, 3]]})

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_analytics_rest(
                "get_video_analytics",
                {"video_id": "vid123", "start_date": "2026-01-01", "end_date": "2026-02-01"},
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["params"]["filters"] == "video==vid123"
    assert captured["params"]["ids"] == "channel==MINE"
    assert "impressions" not in captured["params"]["metrics"]
    assert "views" in captured["params"]["metrics"]
    assert "estimatedMinutesWatched" in captured["params"]["metrics"]
    parsed = json.loads(out)
    assert parsed["rows"] == [[100, 50.0, 30.0, 10, 5.0, 2, 1, 3]]


def test_get_video_analytics_requires_video_id() -> None:
    out = asyncio.run(
        call_youtube_analytics_rest(
            "get_video_analytics", {}, headers={"Authorization": "Bearer tok"}
        )
    )
    assert "video_id required" in out


def test_get_channel_daily_metrics_uses_day_dimension() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["params"] = params
        return _FakeResp(payload={"columnHeaders": [], "rows": []})

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_analytics_rest(
                "get_channel_daily_metrics",
                {"start_date": "2026-01-01", "end_date": "2026-01-31"},
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["params"]["dimensions"] == "day"
    assert captured["params"]["sort"] == "day"
    assert json.loads(out)["rows"] == []


def test_get_top_videos_sorts_by_views_desc() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["params"] = params
        return _FakeResp(payload={"rows": [["vid1", 99]]})

    with patch("httpx.AsyncClient.get", new=fake_get):
        asyncio.run(
            call_youtube_analytics_rest(
                "get_top_videos",
                {"max_results": 5, "start_date": "2026-01-01", "end_date": "2026-01-31"},
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["params"]["dimensions"] == "video"
    assert captured["params"]["sort"] == "-views"
    assert captured["params"]["maxResults"] == 5


def test_query_analytics_report_requires_metrics() -> None:
    out = asyncio.run(
        call_youtube_analytics_rest(
            "query_analytics_report", {}, headers={"Authorization": "Bearer tok"}
        )
    )
    assert "metrics required" in out


def test_401_response_gives_reconnect_hint() -> None:
    async def fake_get(self, url, params=None):
        return _FakeResp(status_code=401, text="Invalid Credentials")

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_analytics_rest(
                "get_video_public_info", {"video_id": "vid123"}, headers={"Authorization": "Bearer tok"}
            )
        )
    assert "401" in out
    assert "Reconecta YouTube Analytics" in out


def test_uses_youtube_analytics_rest_fallback_matches_preset_or_url() -> None:
    assert uses_youtube_analytics_rest_fallback({"preset_id": "google_youtube_analytics"})
    assert uses_youtube_analytics_rest_fallback(
        {"preset_id": "custom", "endpoint_url": "https://youtubeanalytics.googleapis.com/v2/reports"}
    )
    assert not uses_youtube_analytics_rest_fallback({"preset_id": "google_gmail"})


def test_fallback_tool_specs_cover_expected_tools() -> None:
    names = {spec.name for spec in youtube_analytics_rest_fallback_tool_specs()}
    assert names == {
        "list_my_channel_videos",
        "get_video_public_info",
        "get_video_analytics",
        "get_traffic_sources",
        "get_audience_retention",
        "get_channel_daily_metrics",
        "get_top_videos",
        "get_reach_report",
        "query_analytics_report",
    }


def test_reach_report_weights_ctr_by_impressions_and_keeps_newest_file_per_day() -> None:
    csv_old = "date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n20261120,a,999,0.9\n"
    csv_new = "date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n20261120,a,100,0.10\n20261120,b,50,0.02\n"
    csv_d2 = "date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n20261121,a,300,0.02\n"

    async def fake_get(self, url, params=None):
        if url.endswith("/jobs"):
            return _FakeResp(payload={"jobs": [{"id": "j1", "reportTypeId": "channel_reach_basic_a1"}]})
        if url.endswith("/jobs/j1/reports"):
            return _FakeResp(payload={"reports": [
                {"startTime": "2026-11-20T08:00:00Z", "createTime": "2026-11-22T01:00:00Z", "downloadUrl": "old"},
                {"startTime": "2026-11-20T08:00:00Z", "createTime": "2026-11-23T01:00:00Z", "downloadUrl": "new"},
                {"startTime": "2026-11-21T08:00:00Z", "createTime": "2026-11-23T02:00:00Z", "downloadUrl": "d2"},
            ]})
        return _FakeResp(text={"old": csv_old, "new": csv_new, "d2": csv_d2}[url])

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = json.loads(asyncio.run(call_youtube_analytics_rest(
            "get_reach_report", {"start_date": "2026-11-01", "end_date": "2026-11-24"}, headers={"Authorization": "Bearer tok"})))
    # a: 100 imp @10 % + 300 imp @2 % = 16 clicks / 400 = 4 %; the backfilled 999-impression file is ignored
    assert out["videos"] == [{"video_id": "a", "impressions": 400, "ctr_pct": 4.0}, {"video_id": "b", "impressions": 50, "ctr_pct": 2.0}]


def test_reach_report_creates_the_job_when_missing() -> None:
    posted: dict = {}

    async def fake_get(self, url, params=None):
        return _FakeResp(payload={"jobs": []})

    async def fake_post(self, url, json=None):
        posted["body"] = json
        return _FakeResp(payload={"id": "j1"})

    with patch("httpx.AsyncClient.get", new=fake_get), patch("httpx.AsyncClient.post", new=fake_post):
        out = json.loads(asyncio.run(call_youtube_analytics_rest("get_reach_report", {}, headers={"Authorization": "Bearer tok"})))
    assert out["status"] == "job_created"
    assert posted["body"]["reportTypeId"] == "channel_reach_basic_a1"
