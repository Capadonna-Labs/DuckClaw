"""Two connections of the same MCP preset get distinct tool names that fit the 64-char provider limit."""

from duckclaw.forge.skills.mcp_connector_bridge import _public_tool_name
from duckclaw.workers.tool_pack_policy import mcp_connector_ids_from_tool_names


def test_short_names_unchanged() -> None:
    assert _public_tool_name("mcp_google_youtube_analytics", "get_top_videos") == "mcp__google_youtube_analytics__get_top_videos"


def test_named_second_connection_fits_and_stays_distinct() -> None:
    a = _public_tool_name("mcp_google_youtube_analytics_canal_history_machine", "get_audience_retention")
    b = _public_tool_name("mcp_google_youtube_analytics_canal_history_machine_2", "get_audience_retention")
    assert len(a) <= 64 and len(b) <= 64
    assert a != b
    assert a.endswith("__get_audience_retention")
    # each connection still maps to its own tool pack
    assert len(mcp_connector_ids_from_tool_names([a, b])) == 2
