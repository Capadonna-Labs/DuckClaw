"""Per-worker cut of shared MCP connector tools (manifest tool_surface.mcp_tools)."""

from types import SimpleNamespace

from duckclaw.workers.tool_surface_policy import restrict_mcp_connector_tools


def _t(name):
    return SimpleNamespace(name=name)


def test_restricts_only_listed_connectors():
    tools = [_t(n) for n in ("mcp__notion__notion_search", "mcp__notion__notion_create_view",
                             "mcp__github__get_file_contents", "read_sql")]
    spec = SimpleNamespace(tool_surface_config={"mcp_tools": {"notion": ["notion_search"]}})
    kept = [t.name for t in restrict_mcp_connector_tools(tools, spec)]
    assert kept == ["mcp__notion__notion_search", "mcp__github__get_file_contents", "read_sql"]


def test_no_config_keeps_everything():
    tools = [_t("mcp__notion__notion_create_view")]
    assert restrict_mcp_connector_tools(tools, SimpleNamespace(tool_surface_config=None)) == tools
