"""Packaged MCP connector presets (T1 profiles)."""

from __future__ import annotations

from typing import Any

MCP_CONNECTOR_PRESETS: dict[str, dict[str, Any]] = {
    "higgsfield": {
        "display_name": "Higgsfield (imagen/video)",
        "transport": "streamable_http",
        "endpoint_url": "https://mcp.higgsfield.ai/mcp",
        "auth_kind": "bearer",
        "read_only": False,
        "egress_hosts": ["mcp.higgsfield.ai"],
        "tool_allowlist": ["*"],
        "tool_denylist": [],
        "metadata": {
            "docs_url": "https://higgsfield.ai/mcp",
            "auth_hint": "OAuth Higgsfield → Bearer manual en Admin (v1)",
        },
    },
    "mcp_fetch": {
        "display_name": "MCP Fetch (local stdio)",
        "transport": "stdio",
        "launch_command": "npx",
        "launch_args": ["-y", "@modelcontextprotocol/server-fetch"],
        "auth_kind": "none",
        "read_only": True,
        "egress_hosts": [],
        "tool_allowlist": ["*"],
        "tool_denylist": [],
        "metadata": {
            "install": "npx -y @modelcontextprotocol/server-fetch",
        },
    },
    "mcp_time": {
        "display_name": "MCP Time (local stdio)",
        "transport": "stdio",
        "launch_command": "npx",
        "launch_args": ["-y", "@modelcontextprotocol/server-time"],
        "auth_kind": "none",
        "read_only": True,
        "egress_hosts": [],
        "tool_allowlist": ["*"],
        "tool_denylist": [],
        "metadata": {
            "install": "npx -y @modelcontextprotocol/server-time",
        },
    },
}


def list_mcp_connector_presets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for preset_id, body in MCP_CONNECTOR_PRESETS.items():
        out.append({"preset_id": preset_id, **body})
    return out


def preset_payload(preset_id: str) -> dict[str, Any] | None:
    key = (preset_id or "").strip().lower()
    raw = MCP_CONNECTOR_PRESETS.get(key)
    if not raw:
        return None
    return {"preset_id": key, **dict(raw)}
