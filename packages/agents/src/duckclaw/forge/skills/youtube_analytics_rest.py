"""YouTube Data/Analytics via REST — no Google-hosted MCP exists for these APIs.

Same shape as google_gmail_rest.py/google_calendar_rest.py. This preset has no MCP
surface, so the connector bridge registers these tools directly when OAuth is ready
(see google_youtube_analytics in mcp_connector_presets.yaml). Read-only:
youtube.readonly + yt-analytics.readonly scopes only.

Nota de validación: métricas/dimensiones de YouTube Analytics API v2 alineadas con
channel reports públicos (views, estimatedMinutesWatched, averageViewDuration,
averageViewPercentage, likes, shares, comments, subscribersGained;
insightTrafficSourceType; audienceWatchRatio/relativeRetentionPerformance). Si Google
cambia un nombre, el tool devuelve el error crudo de la API en el texto de retorno.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

_YOUTUBE_DATA_BASE = "https://www.googleapis.com/youtube/v3"
_YOUTUBE_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2/reports"

# Core channel/video metrics that combine validly with dimensions=video|day.
_VIDEO_CORE_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "likes,shares,comments,subscribersGained"
)
_CHANNEL_DAILY_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,"
    "likes,shares,comments,subscribersGained,subscribersLost"
)


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _end_date(args: dict[str, Any]) -> str:
    end = str(args.get("end_date") or args.get("endDate") or "").strip()
    return end or date.today().isoformat()


def _start_date(args: dict[str, Any], default: str = "2020-01-01") -> str:
    return str(args.get("start_date") or args.get("startDate") or default).strip() or default


async def call_youtube_analytics_rest(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    token = _bearer(headers)
    if not token:
        return "Error YouTube Analytics REST: missing bearer token"
    args = dict(arguments or {})
    auth = {"Authorization": f"Bearer {token}"}
    name = (tool_name or "").strip()

    async with httpx.AsyncClient(timeout=30.0, headers=auth) as client:
        try:
            if name == "list_my_channel_videos":
                max_results = str(args.get("max_results") or args.get("maxResults") or 15)
                channels_resp = await client.get(
                    f"{_YOUTUBE_DATA_BASE}/channels",
                    params={"part": "snippet,contentDetails,statistics", "mine": "true"},
                )
                if channels_resp.status_code >= 400:
                    resp = channels_resp
                else:
                    items = (channels_resp.json() or {}).get("items") or []
                    if not items:
                        return json.dumps(
                            {"ok": False, "error": "no channel for this account"},
                            ensure_ascii=False,
                        )
                    channel = items[0]
                    uploads_playlist = (
                        channel.get("contentDetails", {})
                        .get("relatedPlaylists", {})
                        .get("uploads")
                    )
                    if not uploads_playlist:
                        return json.dumps(
                            {"ok": False, "error": "uploads playlist not found"},
                            ensure_ascii=False,
                        )
                    playlist_resp = await client.get(
                        f"{_YOUTUBE_DATA_BASE}/playlistItems",
                        params={
                            "part": "snippet,contentDetails",
                            "playlistId": uploads_playlist,
                            "maxResults": max_results,
                        },
                    )
                    if playlist_resp.status_code >= 400:
                        resp = playlist_resp
                    else:
                        payload = playlist_resp.json() or {}
                        payload["channel"] = {
                            "id": channel.get("id"),
                            "title": (channel.get("snippet") or {}).get("title"),
                            "statistics": channel.get("statistics") or {},
                        }
                        return json.dumps(payload, ensure_ascii=False)

            elif name == "get_video_public_info":
                video_id = str(args.get("video_id") or args.get("videoId") or "").strip()
                if not video_id:
                    return "Error YouTube REST: video_id required"
                resp = await client.get(
                    f"{_YOUTUBE_DATA_BASE}/videos",
                    params={"part": "snippet,statistics,contentDetails", "id": video_id},
                )

            elif name == "get_video_analytics":
                video_id = str(args.get("video_id") or args.get("videoId") or "").strip()
                if not video_id:
                    return "Error YouTube Analytics REST: video_id required"
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": _start_date(args),
                        "endDate": _end_date(args),
                        "metrics": _VIDEO_CORE_METRICS,
                        "dimensions": "video",
                        "filters": f"video=={video_id}",
                    },
                )

            elif name == "get_traffic_sources":
                video_id = str(args.get("video_id") or args.get("videoId") or "").strip()
                if not video_id:
                    return "Error YouTube Analytics REST: video_id required"
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": _start_date(args),
                        "endDate": _end_date(args),
                        "metrics": "views",
                        "dimensions": "insightTrafficSourceType",
                        "filters": f"video=={video_id}",
                        "sort": "-views",
                    },
                )

            elif name == "get_audience_retention":
                video_id = str(args.get("video_id") or args.get("videoId") or "").strip()
                if not video_id:
                    return "Error YouTube Analytics REST: video_id required"
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": _start_date(args),
                        "endDate": _end_date(args),
                        "metrics": "audienceWatchRatio,relativeRetentionPerformance",
                        "dimensions": "elapsedVideoTimeRatio",
                        "filters": f"video=={video_id}",
                    },
                )

            elif name == "get_channel_daily_metrics":
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": _start_date(args, default="2024-01-01"),
                        "endDate": _end_date(args),
                        "metrics": _CHANNEL_DAILY_METRICS,
                        "dimensions": "day",
                        "sort": "day",
                    },
                )

            elif name == "get_top_videos":
                max_results = int(args.get("max_results") or args.get("maxResults") or 10)
                max_results = max(1, min(max_results, 50))
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": _start_date(args, default="2024-01-01"),
                        "endDate": _end_date(args),
                        "metrics": _VIDEO_CORE_METRICS,
                        "dimensions": "video",
                        "sort": "-views",
                        "maxResults": max_results,
                    },
                )

            elif name == "query_analytics_report":
                metrics = str(args.get("metrics") or "").strip()
                if not metrics:
                    return "Error YouTube Analytics REST: metrics required"
                params: dict[str, Any] = {
                    "ids": "channel==MINE",
                    "startDate": _start_date(args, default="2024-01-01"),
                    "endDate": _end_date(args),
                    "metrics": metrics,
                }
                dimensions = str(args.get("dimensions") or "").strip()
                if dimensions:
                    params["dimensions"] = dimensions
                filters = str(args.get("filters") or "").strip()
                if filters:
                    params["filters"] = filters
                sort = str(args.get("sort") or "").strip()
                if sort:
                    params["sort"] = sort
                max_results = args.get("max_results") or args.get("maxResults")
                if max_results is not None and str(max_results).strip():
                    params["maxResults"] = int(max_results)
                resp = await client.get(_YOUTUBE_ANALYTICS_BASE, params=params)

            else:
                return f"Error YouTube Analytics REST: unsupported tool {name}"
        except httpx.HTTPError as exc:
            return f"Error YouTube Analytics REST ({name}): {exc}"

        if resp.status_code >= 400:
            if resp.status_code == 401:
                return (
                    f"Error YouTube Analytics REST ({name}): 401 Invalid Credentials. "
                    "Reconecta YouTube Analytics en Admin → MCP Connectors "
                    "(OAuth revocado o expirado)."
                )
            return f"Error YouTube Analytics REST ({name}): {resp.status_code} {resp.text[:400]}"
        if not resp.content:
            return json.dumps({"ok": True}, ensure_ascii=False)
        try:
            return json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            return resp.text


def uses_youtube_analytics_rest_fallback(connector: dict[str, Any]) -> bool:
    preset = str(connector.get("preset_id") or "").strip().lower()
    url = str(connector.get("endpoint_url") or "").strip().lower()
    return preset == "google_youtube_analytics" or "youtubeanalytics.googleapis.com" in url


def youtube_analytics_rest_fallback_tool_specs() -> list[Any]:
    """Static tool surface — YouTube Data/Analytics has no Google-hosted MCP to list_tools."""
    from types import SimpleNamespace

    _video_id = {
        "type": "object",
        "properties": {"video_id": {"type": "string", "description": "YouTube video id"}},
        "required": ["video_id"],
    }
    _video_range = {
        "type": "object",
        "properties": {
            "video_id": {"type": "string", "description": "YouTube video id"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD, default 2020-01-01"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
        },
        "required": ["video_id"],
    }
    _date_range = {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD, default 2024-01-01"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
        },
    }
    return [
        SimpleNamespace(
            name="list_my_channel_videos",
            description=(
                "List recent uploads on the authenticated user's channel, plus channel "
                "title/statistics. Use before analytics to discover video_ids."
            ),
            inputSchema={
                "type": "object",
                "properties": {"max_results": {"type": "integer", "description": "Default 15"}},
            },
        ),
        SimpleNamespace(
            name="get_video_public_info",
            description=(
                "Public metadata for any video (title, views, likes, published date) — "
                "works for videos not owned by the authenticated account too."
            ),
            inputSchema=_video_id,
        ),
        SimpleNamespace(
            name="get_video_analytics",
            description=(
                "Own-channel video analytics for data science: views, watch time, "
                "average view duration/percentage, likes, shares, comments, subscribers "
                "gained. Only works for videos on the authenticated user's own channel."
            ),
            inputSchema=_video_range,
        ),
        SimpleNamespace(
            name="get_traffic_sources",
            description=(
                "Own-channel video traffic sources breakdown (search, suggested, external, etc.)."
            ),
            inputSchema=_video_range,
        ),
        SimpleNamespace(
            name="get_audience_retention",
            description=(
                "Own-channel audience retention curve for one video "
                "(elapsed time ratio vs. watch ratio)."
            ),
            inputSchema=_video_range,
        ),
        SimpleNamespace(
            name="get_channel_daily_metrics",
            description=(
                "Channel-level daily time series for data science: views, watch time, "
                "engagement and subscriber deltas by day. Persist rows in the DuckDB vault "
                "for further SQL analysis."
            ),
            inputSchema=_date_range,
        ),
        SimpleNamespace(
            name="get_top_videos",
            description=(
                "Rank own-channel videos by views in a date range (top N). Good starting "
                "point for comparative data science across titles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default 2024-01-01",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default today",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Default 10, max 50",
                    },
                },
            },
        ),
        SimpleNamespace(
            name="query_analytics_report",
            description=(
                "Flexible YouTube Analytics reports.query for data science. Pass metrics "
                "(required) and optional dimensions/filters/sort/max_results using valid "
                "YouTube Analytics API v2 combinations. Example metrics: "
                "views,estimatedMinutesWatched; dimensions: day or video or country."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "string",
                        "description": "Comma-separated YouTube Analytics metrics",
                    },
                    "dimensions": {
                        "type": "string",
                        "description": (
                            "Optional comma-separated dimensions (day, video, country, …)"
                        ),
                    },
                    "filters": {
                        "type": "string",
                        "description": "Optional filters, e.g. video==VIDEO_ID or country==US",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Optional sort, e.g. -views or day",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default 2024-01-01",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default today",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Optional maxResults",
                    },
                },
                "required": ["metrics"],
            },
        ),
    ]
