from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage

from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

TRUNCATED_BY_SIZE_MARKER = "\n…[truncado por tamaño]"


def compact_run_sandbox_tool_content_for_llm(content: str, max_chars: int) -> str:
    """
    Remove heavy sandbox image payloads before tool output is fed back to the LLM.

    The real image remains carried by graph state; this compacts only the textual
    ToolMessage content used as model context.
    """
    c = content or ""
    s = c.strip()
    if not s.startswith("{"):
        return c if len(c) <= max_chars else c[:max_chars] + TRUNCATED_BY_SIZE_MARKER
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return c if len(c) <= max_chars else c[:max_chars] + TRUNCATED_BY_SIZE_MARKER
    if not isinstance(data, dict):
        return c[:max_chars] + TRUNCATED_BY_SIZE_MARKER
    if data.get("figure_base64"):
        data.pop("figure_base64", None)
    for key in ("output", "stdout", "stderr"):
        if key in data and isinstance(data[key], str) and len(data[key]) > 4000:
            data[key] = data[key][:4000] + "…[truncado]"
    compact = json.dumps(data, ensure_ascii=False)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + TRUNCATED_BY_SIZE_MARKER


def truncate_tool_messages_for_llm(messages: list[Any], max_chars: int) -> list[Any]:
    out: list[Any] = []
    for message in messages or []:
        if not isinstance(message, ToolMessage) or max_chars <= 0:
            out.append(message)
            continue

        content = message.content
        if not isinstance(content, str):
            out.append(message)
            continue

        name = getattr(message, "name", "") or ""
        original_content = content
        if name.startswith("reddit_"):
            content = format_reddit_mcp_reply_if_applicable(content)

        if name in ("run_sandbox", "run_browser_sandbox"):
            compacted = compact_run_sandbox_tool_content_for_llm(content, max_chars)
            out.append(
                ToolMessage(
                    content=compacted,
                    tool_call_id=message.tool_call_id,
                    name=name,
                )
            )
        elif len(content) > max_chars:
            out.append(
                ToolMessage(
                    content=content[:max_chars] + TRUNCATED_BY_SIZE_MARKER,
                    tool_call_id=message.tool_call_id,
                    name=name,
                )
            )
        elif content != original_content:
            out.append(
                ToolMessage(
                    content=content,
                    tool_call_id=message.tool_call_id,
                    name=name,
                )
            )
        else:
            out.append(message)
    return out


__all__ = [
    "TRUNCATED_BY_SIZE_MARKER",
    "compact_run_sandbox_tool_content_for_llm",
    "truncate_tool_messages_for_llm",
]
