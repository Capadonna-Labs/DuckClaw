from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage

from duckclaw.workers.reddit_formatters import format_reddit_mcp_reply_if_applicable

TRUNCATED_BY_SIZE_MARKER = "\n…[truncado por tamaño]"

_HOMEOSTASIS_TOOL_NAMES = frozenset(
    {
        "evaluate_homeostasis",
        "evaluate_tp_sl_monitor",
        "read_tp_sl_levels",
    }
)


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


def compact_homeostasis_tool_content_for_llm(content: str, max_chars: int) -> str:
    """
    Keep tp_sl_monitor.levels when shrinking evaluate_homeostasis for context.

    Naive head-truncation drops levels (they sit after a large goals blob) and
    breaks mechanical TP/SL rewrite (anonymous calculate_tp_sl_distance collapse).
    """
    c = content or ""
    s = c.strip()
    if max_chars <= 0:
        return c
    if len(c) <= max_chars:
        return c
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return c[:max_chars] + TRUNCATED_BY_SIZE_MARKER
    if not isinstance(data, dict):
        return c[:max_chars] + TRUNCATED_BY_SIZE_MARKER

    mon = data.get("tp_sl_monitor") if isinstance(data.get("tp_sl_monitor"), dict) else None
    levels = None
    if mon is not None and isinstance(mon.get("levels"), list):
        levels = mon.get("levels")
    elif isinstance(data.get("levels"), list):
        levels = data.get("levels")

    slim: dict[str, Any] = {
        "status": data.get("status") or data.get("ok"),
        "homeostasis_achieved": data.get("homeostasis_achieved"),
        "metrics_aligned": data.get("metrics_aligned"),
        "hitl_required": data.get("hitl_required"),
        "current_metrics": data.get("current_metrics"),
        "deviations": data.get("deviations"),
        "loop_mode_hint": data.get("loop_mode_hint"),
        "tp_sl_alerts": data.get("tp_sl_alerts") or (mon or {}).get("alerts"),
    }
    if mon is not None:
        slim_mon = {
            k: mon.get(k)
            for k in (
                "active_count",
                "open_positions_count",
                "coverage_gap",
                "uncovered_tickers",
                "pending_evaluation",
                "accepted_gaps",
                "alerts",
            )
            if k in mon
        }
        slim_mon["levels"] = levels or []
        slim["tp_sl_monitor"] = slim_mon
    elif levels is not None:
        slim["levels"] = levels

    compact = json.dumps(slim, ensure_ascii=False)
    if len(compact) <= max_chars:
        return compact
    # Last resort: levels-only payload for egress rewrite + minimal LLM context.
    if levels is not None:
        levels_only = json.dumps(
            {"status": slim.get("status"), "tp_sl_monitor": {"levels": levels}},
            ensure_ascii=False,
        )
        if len(levels_only) <= max_chars:
            return levels_only
        # Keep as many complete level rows as fit.
        kept: list[Any] = []
        for row in levels:
            trial = kept + [row]
            candidate = json.dumps(
                {"status": slim.get("status"), "tp_sl_monitor": {"levels": trial}},
                ensure_ascii=False,
            )
            if len(candidate) > max_chars:
                break
            kept = trial
        if kept:
            return json.dumps(
                {"status": slim.get("status"), "tp_sl_monitor": {"levels": kept}},
                ensure_ascii=False,
            )
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
        elif name in _HOMEOSTASIS_TOOL_NAMES:
            compacted = compact_homeostasis_tool_content_for_llm(content, max_chars)
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
    "compact_homeostasis_tool_content_for_llm",
    "compact_run_sandbox_tool_content_for_llm",
    "truncate_tool_messages_for_llm",
]
