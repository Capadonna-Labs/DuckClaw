"""YouTube Data API v3 via REST — trending / search / categories for data science.

Shares the google_youtube_analytics connector OAuth (youtube.readonly already granted).
Analytics reports stay in youtube_analytics_rest.py; this module covers global/public
surfaces the Analytics API cannot: chart=mostPopular, search.list, videoCategories.

Nota de validación: parámetros alineados con YouTube Data API v3
(videos.list chart=mostPopular, search.list, videoCategories.list). Errores de Google
se devuelven crudos en el texto de retorno.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_YOUTUBE_DATA_BASE = "https://www.googleapis.com/youtube/v3"

YOUTUBE_DATA_REST_TOOL_NAMES = frozenset(
    {
        "list_trending_videos",
        "search_youtube",
        "list_video_categories",
        "get_videos_by_ids",
        "get_channel_public_info",
    }
)


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _clamp_max_results(args: dict[str, Any], default: int = 25, hard_max: int = 50) -> int:
    raw = args.get("max_results") if args.get("max_results") is not None else args.get("maxResults")
    try:
        n = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, hard_max))


async def call_youtube_data_rest(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    token = _bearer(headers)
    if not token:
        return "Error YouTube Data REST: missing bearer token"
    args = dict(arguments or {})
    auth = {"Authorization": f"Bearer {token}"}
    name = (tool_name or "").strip()

    async with httpx.AsyncClient(timeout=30.0, headers=auth) as client:
        try:
            if name == "list_trending_videos":
                region = str(args.get("region_code") or args.get("regionCode") or "US").strip().upper()
                params: dict[str, Any] = {
                    "part": "snippet,statistics,contentDetails",
                    "chart": "mostPopular",
                    "regionCode": region or "US",
                    "maxResults": _clamp_max_results(args, default=25),
                }
                category = str(args.get("category_id") or args.get("categoryId") or "").strip()
                if category:
                    params["videoCategoryId"] = category
                resp = await client.get(f"{_YOUTUBE_DATA_BASE}/videos", params=params)

            elif name == "search_youtube":
                query = str(args.get("query") or args.get("q") or "").strip()
                if not query:
                    return "Error YouTube Data REST: query required"
                params = {
                    "part": "snippet",
                    "q": query,
                    "type": str(args.get("type") or "video").strip() or "video",
                    "maxResults": _clamp_max_results(args, default=25),
                }
                region = str(args.get("region_code") or args.get("regionCode") or "").strip().upper()
                if region:
                    params["regionCode"] = region
                lang = str(args.get("relevance_language") or args.get("relevanceLanguage") or "").strip()
                if lang:
                    params["relevanceLanguage"] = lang
                order = str(args.get("order") or "").strip()
                if order:
                    params["order"] = order
                published_after = str(
                    args.get("published_after") or args.get("publishedAfter") or ""
                ).strip()
                if published_after:
                    params["publishedAfter"] = published_after
                channel_id = str(args.get("channel_id") or args.get("channelId") or "").strip()
                if channel_id:
                    params["channelId"] = channel_id
                resp = await client.get(f"{_YOUTUBE_DATA_BASE}/search", params=params)

            elif name == "list_video_categories":
                region = str(args.get("region_code") or args.get("regionCode") or "US").strip().upper()
                resp = await client.get(
                    f"{_YOUTUBE_DATA_BASE}/videoCategories",
                    params={"part": "snippet", "regionCode": region or "US"},
                )

            elif name == "get_videos_by_ids":
                raw_ids = args.get("video_ids") or args.get("videoIds") or args.get("id") or ""
                if isinstance(raw_ids, list):
                    ids = [str(x).strip() for x in raw_ids if str(x).strip()]
                else:
                    ids = [p.strip() for p in str(raw_ids).split(",") if p.strip()]
                if not ids:
                    return "Error YouTube Data REST: video_ids required"
                # API allows up to 50 ids per call.
                ids = ids[:50]
                resp = await client.get(
                    f"{_YOUTUBE_DATA_BASE}/videos",
                    params={
                        "part": "snippet,statistics,contentDetails,topicDetails",
                        "id": ",".join(ids),
                    },
                )

            elif name == "get_channel_public_info":
                channel_id = str(args.get("channel_id") or args.get("channelId") or "").strip()
                handle = str(args.get("for_handle") or args.get("forHandle") or "").strip()
                username = str(args.get("for_username") or args.get("forUsername") or "").strip()
                params = {"part": "snippet,statistics,contentDetails,brandingSettings"}
                if channel_id:
                    params["id"] = channel_id
                elif handle:
                    # Data API accepts forHandle without leading @ in recent versions; strip if present.
                    params["forHandle"] = handle.lstrip("@")
                elif username:
                    params["forUsername"] = username
                else:
                    return "Error YouTube Data REST: channel_id, for_handle, or for_username required"
                resp = await client.get(f"{_YOUTUBE_DATA_BASE}/channels", params=params)

            else:
                return f"Error YouTube Data REST: unsupported tool {name}"
        except httpx.HTTPError as exc:
            return f"Error YouTube Data REST ({name}): {exc}"

        if resp.status_code >= 400:
            if resp.status_code == 401:
                return (
                    f"Error YouTube Data REST ({name}): 401 Invalid Credentials. "
                    "Reconecta YouTube Analytics en Admin → MCP Connectors "
                    "(OAuth revocado o expirado; scope youtube.readonly)."
                )
            return f"Error YouTube Data REST ({name}): {resp.status_code} {resp.text[:400]}"
        if not resp.content:
            return json.dumps({"ok": True}, ensure_ascii=False)
        try:
            return json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            return resp.text


def uses_youtube_data_rest_fallback(connector: dict[str, Any]) -> bool:
    """Same connector as Analytics — youtube.readonly unlocks Data API trending/search."""
    preset = str(connector.get("preset_id") or "").strip().lower()
    url = str(connector.get("endpoint_url") or "").strip().lower()
    return (
        preset == "google_youtube_analytics"
        or "youtubeanalytics.googleapis.com" in url
        or "googleapis.com/youtube" in url
    )


def youtube_data_rest_fallback_tool_specs() -> list[Any]:
    """Static Data API tool surface for global trends / clustering features."""
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            name="list_trending_videos",
            description=(
                "Global/regional YouTube trending (chart=mostPopular) for data science and "
                "clustering. Optional region_code (ISO 3166-1, default US) and category_id. "
                "Returns snippet + statistics + contentDetails for each video."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "region_code": {
                        "type": "string",
                        "description": "ISO country code, e.g. US, MX, ES, CO. Default US",
                    },
                    "category_id": {
                        "type": "string",
                        "description": "Optional YouTube videoCategoryId (from list_video_categories)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Default 25, max 50",
                    },
                },
            },
        ),
        SimpleNamespace(
            name="search_youtube",
            description=(
                "YouTube search.list for keywords/topics (global discovery). Returns search "
                "snippets; follow up with get_videos_by_ids for full statistics suitable for "
                "clustering. Optional region_code, relevance_language, order, published_after, "
                "channel_id, type (video|channel|playlist)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "region_code": {"type": "string", "description": "Optional ISO country code"},
                    "relevance_language": {
                        "type": "string",
                        "description": "Optional BCP-47 language, e.g. es, en",
                    },
                    "order": {
                        "type": "string",
                        "description": "date|rating|relevance|title|videoCount|viewCount",
                    },
                    "published_after": {
                        "type": "string",
                        "description": "RFC 3339 datetime, e.g. 2026-01-01T00:00:00Z",
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Optional restrict results to one channel",
                    },
                    "type": {
                        "type": "string",
                        "description": "video (default), channel, or playlist",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Default 25, max 50",
                    },
                },
                "required": ["query"],
            },
        ),
        SimpleNamespace(
            name="list_video_categories",
            description=(
                "List YouTube video categories for a region (ids for list_trending_videos "
                "category_id filter). Useful before regional clustering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "region_code": {
                        "type": "string",
                        "description": "ISO country code, default US",
                    },
                },
            },
        ),
        SimpleNamespace(
            name="get_videos_by_ids",
            description=(
                "Batch fetch public video details (snippet, statistics, contentDetails, "
                "topicDetails) for up to 50 ids. Use after search_youtube to build feature "
                "tables for clustering in the DuckDB vault."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_ids": {
                        "type": "string",
                        "description": "Comma-separated YouTube video ids (max 50)",
                    },
                },
                "required": ["video_ids"],
            },
        ),
        SimpleNamespace(
            name="get_channel_public_info",
            description=(
                "Public channel metadata and statistics by channel_id, for_handle, or "
                "for_username. Useful for competitor / niche context alongside trending."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "YouTube channel id"},
                    "for_handle": {
                        "type": "string",
                        "description": "Channel handle, with or without @",
                    },
                    "for_username": {
                        "type": "string",
                        "description": "Legacy YouTube username",
                    },
                },
            },
        ),
    ]
