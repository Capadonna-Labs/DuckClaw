"""Registro de tools YouTube transcript MCP (allowlist read-only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from duckclaw.forge.skills import youtube_transcript_bridge as ytb


def _tool(name: str) -> MagicMock:
    spec = MagicMock()
    spec.name = name
    spec.description = f"tool {name}"
    spec.inputSchema = {"type": "object", "properties": {"url": {"type": "string"}}}
    return spec


def test_connect_youtube_transcript_mcp_filters_allowlist() -> None:
    specs = [
        _tool("get_transcript"),
        _tool("get_timed_transcript"),
        _tool("get_video_info"),
        _tool("get_available_languages"),
        _tool("unknown_tool"),
    ]
    with patch.object(ytb, "_mcp_available", return_value=True), patch.object(
        ytb, "_uvx_available", return_value=True
    ), patch(
        "duckclaw.forge.skills.mcp_stdio_util.mcp_stdio_list_tools",
        new=AsyncMock(return_value=specs),
    ):
        tools = __import__("asyncio").run(ytb.connect_youtube_transcript_mcp(manifest_config={}))
    names = {getattr(t, "name", "") for t in tools}
    assert names == {
        "get_transcript",
        "get_timed_transcript",
        "get_video_info",
        "get_available_languages",
    }


def test_connect_youtube_transcript_mcp_manifest_tools_whitelist() -> None:
    specs = [
        _tool("get_transcript"),
        _tool("get_timed_transcript"),
        _tool("get_video_info"),
        _tool("get_available_languages"),
    ]
    with patch.object(ytb, "_mcp_available", return_value=True), patch.object(
        ytb, "_uvx_available", return_value=True
    ), patch(
        "duckclaw.forge.skills.mcp_stdio_util.mcp_stdio_list_tools",
        new=AsyncMock(return_value=specs),
    ):
        tools = __import__("asyncio").run(
            ytb.connect_youtube_transcript_mcp(
                manifest_config={"tools": ["get_transcript"]},
            )
        )
    names = {getattr(t, "name", "") for t in tools}
    assert names == {"get_transcript"}


def test_connect_youtube_transcript_mcp_graceful_without_uvx() -> None:
    with patch.object(ytb, "_mcp_available", return_value=True), patch.object(
        ytb, "_uvx_available", return_value=False
    ):
        tools = __import__("asyncio").run(ytb.connect_youtube_transcript_mcp())
    assert tools == []
