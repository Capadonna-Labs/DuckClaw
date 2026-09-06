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
        return _FakeResp(payload={"rows": [[100, 50.0, 30.0, 10, 5.0, 2]]})

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
    parsed = json.loads(out)
    assert parsed["rows"] == [[100, 50.0, 30.0, 10, 5.0, 2]]


def test_get_video_analytics_requires_video_id() -> None:
    out = asyncio.run(
        call_youtube_analytics_rest(
            "get_video_analytics", {}, headers={"Authorization": "Bearer tok"}
        )
    )
    assert "video_id required" in out


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
    }
