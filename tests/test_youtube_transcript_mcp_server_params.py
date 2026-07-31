"""Resolución de comando stdio para mcp-youtube-transcript (uvx)."""

from __future__ import annotations

import os
from unittest.mock import patch

from duckclaw.forge.skills import youtube_transcript_bridge as ytb


def test_youtube_transcript_mcp_server_params_default_uvx() -> None:
    params = ytb.youtube_transcript_mcp_server_params({"response_limit": 12000})
    assert params.command == "uvx"
    assert params.args == [
        "--from",
        "git+https://github.com/jkawamoto/mcp-youtube-transcript",
        "--with",
        "mcp>=1.9,<2",
        "mcp-youtube-transcript",
        "--response-limit",
        "12000",
    ]


def test_youtube_transcript_mcp_server_params_custom_command_override() -> None:
    with patch.dict(
        os.environ,
        {
            "DUCKCLAW_YOUTUBE_TRANSCRIPT_MCP_COMMAND": "/usr/bin/uvx",
            "DUCKCLAW_YOUTUBE_TRANSCRIPT_MCP_ARGS": "mcp-youtube-transcript --help",
        },
        clear=False,
    ):
        params = ytb.youtube_transcript_mcp_server_params({})
    assert params.command == "/usr/bin/uvx"
    assert params.args == ["mcp-youtube-transcript", "--help"]


def test_response_limit_clamped() -> None:
    params = ytb.youtube_transcript_mcp_server_params({"response_limit": 999999})
    assert params.args[-1] == "50000"


def test_youtube_transcript_mcp_server_params_https_proxy() -> None:
    params = ytb.youtube_transcript_mcp_server_params(
        {"response_limit": 15000, "https_proxy": "http://proxy.example:8080"}
    )
    assert "--https-proxy" in params.args
    assert params.args[params.args.index("--https-proxy") + 1] == "http://proxy.example:8080"
    assert params.env.get("HTTPS_PROXY") == "http://proxy.example:8080"


def test_normalize_youtube_tool_result_rate_limit() -> None:
    raw = "Error: 429 Client Error: Too Many Requests for url: https://www.google.com/sorry/index"
    out = ytb._normalize_youtube_tool_result(raw)
    assert out.startswith("YOUTUBE_RATE_LIMIT:")
    assert "web_search" in out

