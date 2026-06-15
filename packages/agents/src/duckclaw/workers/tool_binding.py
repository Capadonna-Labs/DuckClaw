from __future__ import annotations

from typing import Any


def tool_choice_function(tool_name: str) -> dict[str, Any]:
    """OpenAI-compatible forced function tool_choice for a tool name."""
    name = str(tool_name or "").strip()
    return {"type": "function", "function": {"name": name}}


def tool_called_since(messages: list[Any], last_human_idx: int, tool_name: str) -> bool:
    """Return whether a ToolMessage with this name appears after the last human turn."""
    from langchain_core.messages import ToolMessage

    name = str(tool_name or "").strip()
    if not name:
        return False
    for msg in (messages or [])[max(0, last_human_idx + 1) :]:
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == name:
            return True
    return False


def groq_tools_without_reddit_for_bind(tools: list[Any]) -> list[Any]:
    """
    Groq's on-demand tier counts tool definitions in the request budget.

    Generic Groq routes bind without reddit_* tools; forced Reddit routes can
    still bind the complete tool set from the worker assembly.
    """
    return [
        tool
        for tool in (tools or [])
        if not str(getattr(tool, "name", None) or "").startswith("reddit_")
    ]


def filter_tools_for_sandbox(tools: list[Any], enabled: bool) -> list[Any]:
    """Remove sandbox tools from the LLM bind surface when sandbox is disabled."""
    if enabled:
        return list(tools)
    deny = {
        "run_sandbox",
        "run_browser_sandbox",
        "get_browser_session_url",
    }
    return [tool for tool in tools if getattr(tool, "name", "") not in deny]


__all__ = [
    "filter_tools_for_sandbox",
    "groq_tools_without_reddit_for_bind",
    "tool_called_since",
    "tool_choice_function",
]
