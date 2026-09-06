"""YouTube Data/Analytics via REST — no Google-hosted MCP exists for these APIs.

Same shape as google_gmail_rest.py/google_calendar_rest.py (REST fallback registered when
tools/list against the connector's placeholder endpoint_url fails, which for this preset is
always — see google_youtube_analytics in mcp_connector_presets.yaml). Read-only: youtube.readonly
+ yt-analytics.readonly scopes only.

Nota de validación: nombres de dimensiones/métricas de YouTube Analytics API v2 confirmados
contra la referencia pública al momento de escribir esto; si Google los cambia, los tools
devuelven el error crudo de la API (visible en el texto de retorno), no una excepción silenciosa.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_YOUTUBE_DATA_BASE = "https://www.googleapis.com/youtube/v3"
_YOUTUBE_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2/reports"


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


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
                    params={"part": "contentDetails", "mine": "true"},
                )
                if channels_resp.status_code >= 400:
                    resp = channels_resp
                else:
                    items = (channels_resp.json() or {}).get("items") or []
                    if not items:
                        return json.dumps({"ok": False, "error": "no channel for this account"}, ensure_ascii=False)
                    uploads_playlist = (
                        items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                    )
                    if not uploads_playlist:
                        return json.dumps({"ok": False, "error": "uploads playlist not found"}, ensure_ascii=False)
                    resp = await client.get(
                        f"{_YOUTUBE_DATA_BASE}/playlistItems",
                        params={
                            "part": "snippet,contentDetails",
                            "playlistId": uploads_playlist,
                            "maxResults": max_results,
                        },
                    )

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
                start_date = str(args.get("start_date") or args.get("startDate") or "2020-01-01")
                end_date = str(args.get("end_date") or args.get("endDate") or "").strip()
                if not video_id:
                    return "Error YouTube Analytics REST: video_id required"
                if not end_date:
                    from datetime import date

                    end_date = date.today().isoformat()
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": start_date,
                        "endDate": end_date,
                        "metrics": (
                            "views,estimatedMinutesWatched,averageViewDuration,"
                            "impressions,impressionsClickThroughRate,subscribersGained"
                        ),
                        "dimensions": "video",
                        "filters": f"video=={video_id}",
                    },
                )

            elif name == "get_traffic_sources":
                video_id = str(args.get("video_id") or args.get("videoId") or "").strip()
                start_date = str(args.get("start_date") or args.get("startDate") or "2020-01-01")
                end_date = str(args.get("end_date") or args.get("endDate") or "").strip()
                if not video_id:
                    return "Error YouTube Analytics REST: video_id required"
                if not end_date:
                    from datetime import date

                    end_date = date.today().isoformat()
                resp = await client.get(
                    _YOUTUBE_ANALYTICS_BASE,
                    params={
                        "ids": "channel==MINE",
                        "startDate": start_date,
                        "endDate": end_date,
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
                        "startDate": "2020-01-01",
                        "endDate": "2030-01-01",
                        "metrics": "audienceWatchRatio,relativeRetentionPerformance",
                        "dimensions": "elapsedVideoTimeRatio",
                        "filters": f"video=={video_id}",
                    },
                )

            else:
                return f"Error YouTube Analytics REST: unsupported tool {name}"
        except httpx.HTTPError as exc:
            return f"Error YouTube Analytics REST ({name}): {exc}"

        if resp.status_code >= 400:
            if resp.status_code == 401:
                return (
                    f"Error YouTube Analytics REST ({name}): 401 Invalid Credentials. "
                    "Reconecta YouTube Analytics en Admin → MCP Connectors (OAuth revocado o expirado)."
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
    return [
        SimpleNamespace(
            name="list_my_channel_videos",
            description="List recent videos uploaded to the authenticated user's own channel.",
            inputSchema={
                "type": "object",
                "properties": {"max_results": {"type": "integer", "description": "Default 15"}},
            },
        ),
        SimpleNamespace(
            name="get_video_public_info",
            description="Public metadata for any video (title, views, likes, published date) — works for videos not owned by the authenticated account too.",
            inputSchema=_video_id,
        ),
        SimpleNamespace(
            name="get_video_analytics",
            description=(
                "Own-channel video analytics: views, watch time, average view duration, "
                "impressions, impressions CTR, subscribers gained. Only works for videos on "
                "the authenticated user's own channel."
            ),
            inputSchema=_video_range,
        ),
        SimpleNamespace(
            name="get_traffic_sources",
            description="Own-channel video traffic sources breakdown (search, suggested, external, etc.).",
            inputSchema=_video_range,
        ),
        SimpleNamespace(
            name="get_audience_retention",
            description="Own-channel audience retention curve for one video (elapsed time ratio vs. watch ratio).",
            inputSchema=_video_id,
        ),
    ]
