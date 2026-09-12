"""Tests for YouTube Data API v3 REST bridge (trending / search / categories)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from duckclaw.forge.skills.youtube_data_rest import (
    YOUTUBE_DATA_REST_TOOL_NAMES,
    call_youtube_data_rest,
    uses_youtube_data_rest_fallback,
    youtube_data_rest_fallback_tool_specs,
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
    out = asyncio.run(call_youtube_data_rest("list_trending_videos", {"region_code": "US"}, headers=None))
    assert "missing bearer token" in out


def test_unsupported_tool_returns_error() -> None:
    async def fake_get(self, url, params=None):
        raise AssertionError("should not call HTTP for an unsupported tool")

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_data_rest(
                "not_a_real_tool", {}, headers={"Authorization": "Bearer tok"}
            )
        )
    assert "unsupported tool" in out


def test_list_trending_videos_uses_most_popular_chart() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp(payload={"items": [{"id": "abc"}]})

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_data_rest(
                "list_trending_videos",
                {"region_code": "mx", "category_id": "10", "max_results": 12},
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["url"].endswith("/videos")
    assert captured["params"]["chart"] == "mostPopular"
    assert captured["params"]["regionCode"] == "MX"
    assert captured["params"]["videoCategoryId"] == "10"
    assert captured["params"]["maxResults"] == 12
    assert json.loads(out)["items"][0]["id"] == "abc"


def test_search_youtube_requires_query() -> None:
    out = asyncio.run(
        call_youtube_data_rest("search_youtube", {}, headers={"Authorization": "Bearer tok"})
    )
    assert "query required" in out


def test_search_youtube_passes_query_and_filters() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp(payload={"items": []})

    with patch("httpx.AsyncClient.get", new=fake_get):
        asyncio.run(
            call_youtube_data_rest(
                "search_youtube",
                {
                    "query": "ai agents",
                    "region_code": "ES",
                    "order": "viewCount",
                    "published_after": "2026-01-01T00:00:00Z",
                },
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["url"].endswith("/search")
    assert captured["params"]["q"] == "ai agents"
    assert captured["params"]["regionCode"] == "ES"
    assert captured["params"]["order"] == "viewCount"
    assert captured["params"]["publishedAfter"] == "2026-01-01T00:00:00Z"


def test_get_videos_by_ids_requires_ids() -> None:
    out = asyncio.run(
        call_youtube_data_rest("get_videos_by_ids", {}, headers={"Authorization": "Bearer tok"})
    )
    assert "video_ids required" in out


def test_get_videos_by_ids_batches_comma_list() -> None:
    captured: dict = {}

    async def fake_get(self, url, params=None):
        captured["params"] = params
        return _FakeResp(payload={"items": [{"id": "a"}, {"id": "b"}]})

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_data_rest(
                "get_videos_by_ids",
                {"video_ids": "a, b, c"},
                headers={"Authorization": "Bearer tok"},
            )
        )

    assert captured["params"]["id"] == "a,b,c"
    assert "topicDetails" in captured["params"]["part"]
    assert len(json.loads(out)["items"]) == 2


def test_get_channel_public_info_requires_identifier() -> None:
    out = asyncio.run(
        call_youtube_data_rest(
            "get_channel_public_info", {}, headers={"Authorization": "Bearer tok"}
        )
    )
    assert "channel_id" in out


def test_401_response_gives_reconnect_hint() -> None:
    async def fake_get(self, url, params=None):
        return _FakeResp(status_code=401, text="Invalid Credentials")

    with patch("httpx.AsyncClient.get", new=fake_get):
        out = asyncio.run(
            call_youtube_data_rest(
                "list_video_categories",
                {"region_code": "US"},
                headers={"Authorization": "Bearer tok"},
            )
        )
    assert "401" in out
    assert "Reconecta YouTube Analytics" in out


def test_uses_youtube_data_rest_fallback_matches_analytics_preset() -> None:
    assert uses_youtube_data_rest_fallback({"preset_id": "google_youtube_analytics"})
    assert uses_youtube_data_rest_fallback(
        {"preset_id": "custom", "endpoint_url": "https://youtubeanalytics.googleapis.com/v2/reports"}
    )
    assert not uses_youtube_data_rest_fallback({"preset_id": "google_gmail"})


def test_fallback_tool_specs_cover_expected_tools() -> None:
    names = {spec.name for spec in youtube_data_rest_fallback_tool_specs()}
    assert names == YOUTUBE_DATA_REST_TOOL_NAMES


def test_connect_worker_mcp_registers_youtube_data_and_analytics_rest() -> None:
    """YouTube has no hosted MCP — both REST surfaces register when OAuth is ready."""
    from unittest.mock import MagicMock, patch

    from duckclaw.forge.skills import mcp_connector_bridge as bridge
    from duckclaw.forge.skills.youtube_analytics_rest import (
        youtube_analytics_rest_fallback_tool_specs,
    )

    connector = {
        "connector_id": "mcp_google_youtube_analytics",
        "preset_id": "google_youtube_analytics",
        "endpoint_url": "https://youtubeanalytics.googleapis.com/v2/reports",
        "transport": "streamable_http",
        "auth_kind": "bearer",
    }
    db = MagicMock()

    with patch.object(bridge, "list_worker_mcp_connectors", return_value=[connector]):
        with patch.object(bridge, "resolve_connector_bearer_token", return_value="tok"):
            with patch.object(bridge, "_mcp_available", return_value=True):
                tools = asyncio.run(
                    bridge.connect_worker_mcp_connectors(
                        db, worker_uid="uid", tenant_id="default"
                    )
                )

    names = {getattr(t, "name", "") for t in tools}
    assert any(n.endswith("__list_trending_videos") for n in names)
    assert any(n.endswith("__search_youtube") for n in names)
    assert any(n.endswith("__list_my_channel_videos") for n in names)
    expected = len(youtube_data_rest_fallback_tool_specs()) + len(
        youtube_analytics_rest_fallback_tool_specs()
    )
    assert len(tools) == expected
