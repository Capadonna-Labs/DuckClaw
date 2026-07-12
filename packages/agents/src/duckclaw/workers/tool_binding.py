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


_MLX_BIND_PRIORITY_TOOL_NAMES: tuple[str, ...] = (
    "read_sql",
    "inspect_schema",
    "get_schema_info",
    "tavily_search",
    "run_sandbox",
    "execute_sandbox_script",
    "catalog_retriever",
    "assess_crons_alignment",
)


def mlx_tools_for_bind(tools: list[Any], *, max_tools: int | None = None) -> list[Any]:
    """
    Cap tool schemas for local MLX/Metal — runtime showed ~350 tokens/tool and
    147 tools pushed ~68k prompts despite ~17k message budget.
    """
    from duckclaw.workers.provider_input_budget import mlx_max_bound_tools

    cap = max(1, int(max_tools if max_tools is not None else mlx_max_bound_tools()))
    src = list(tools or [])
    if len(src) <= cap:
        return src
    by_name = {str(getattr(t, "name", "") or ""): t for t in src}
    picked: list[Any] = []
    seen: set[str] = set()
    for name in _MLX_BIND_PRIORITY_TOOL_NAMES:
        tool = by_name.get(name)
        if tool is not None and name not in seen:
            picked.append(tool)
            seen.add(name)
    for tool in src:
        name = str(getattr(tool, "name", "") or "")
        if name in seen:
            continue
        picked.append(tool)
        seen.add(name)
        if len(picked) >= cap:
            break
    return picked[:cap]


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
    "mlx_tools_for_bind",
    "tool_called_since",
    "tool_choice_function",
]
