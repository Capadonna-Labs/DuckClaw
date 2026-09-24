"""Stop repeated read_sql/admin_sql thrash that burns the turn wall-clock.

Quant "profundiza X" turns were looping read_sql on the same OHLCV slice until
Gateway sat at 100% CPU and the UI looked hung. After N SQL tools since the
last human message, clear force flags and unbind SQL so the model must answer.
"""

from __future__ import annotations

import os
from typing import Any

_SQL_TOOL_NAMES = frozenset({"read_sql", "admin_sql", "inspect_schema"})


def sql_thrash_limit() -> int:
    """Max SQL tool calls per user turn before synthesis-only (floor 2)."""
    try:
        return max(2, int(float(os.environ.get("DUCKCLAW_READ_SQL_THRASH_LIMIT") or "3")))
    except (TypeError, ValueError):
        return 3


def count_sql_tools_since_last_human(messages: list[Any]) -> int:
    try:
        from duckclaw.workers.tool_orchestration import (
            _last_human_index,
            _tools_since,
        )
    except Exception:
        return 0
    msgs = list(messages or [])
    ran = _tools_since(msgs, _last_human_index(msgs))
    return sum(1 for n in ran if str(n) in _SQL_TOOL_NAMES)


def is_sql_thrash(messages: list[Any], *, limit: int | None = None) -> bool:
    lim = sql_thrash_limit() if limit is None else max(2, int(limit))
    return count_sql_tools_since_last_human(messages) >= lim


def build_sql_thrash_detente_message(*, count: int, limit: int) -> str:
    return (
        "[SYSTEM_EVENT: SQL_THRASH_DETENTE] "
        f"Ya corriste {count} tools SQL en este turno (límite {limit}). "
        "PROHIBIDO llamar read_sql/admin_sql/inspect_schema otra vez. "
        "Sintetiza la respuesta al usuario con lo que ya tienes "
        "(máx ~25 líneas). Si faltan datos, dilo en prosa y pregunta."
    )


def strip_sql_tools(tools: list[Any]) -> list[Any]:
    return [
        t
        for t in tools
        if str(getattr(t, "name", "") or "") not in _SQL_TOOL_NAMES
    ]


def maybe_apply_sql_thrash_tool_guard(
    tools: list[Any],
    messages: list[Any],
) -> tuple[list[Any], bool, str | None]:
    """If SQL thrash, strip SQL tools and return a DETENTE system prompt.

    Returns (tools, applied, detente_message_or_none).
    """
    count = count_sql_tools_since_last_human(messages)
    limit = sql_thrash_limit()
    if count < limit:
        return tools, False, None
    return (
        strip_sql_tools(tools),
        True,
        build_sql_thrash_detente_message(count=count, limit=limit),
    )


def clear_sql_forces_if_thrash(
    messages: list[Any],
    *,
    force_orch_tool: str | None,
    force_schema: bool,
    force_admin_sql: bool,
    force_read_sql: bool,
) -> tuple[str | None, bool, bool, bool]:
    """Clear SQL force flags once thrash limit is hit (so force path cannot re-bind)."""
    if not is_sql_thrash(messages):
        return force_orch_tool, force_schema, force_admin_sql, force_read_sql
    orch = str(force_orch_tool or "").strip()
    if orch in _SQL_TOOL_NAMES:
        force_orch_tool = None
    return force_orch_tool, False, False, False


def apply_auto_bind_tool_guards(
    tools: list[Any],
    messages: list[Any],
    *,
    loop_system_event: bool,
    llm_messages: list[Any],
    groq_messages: list[Any] | None = None,
) -> tuple[list[Any], bool, list[Any], list[Any] | None, bool]:
    """Post-pack auto-bind filters: /loop HITL-only + SQL thrash DETENTE.

    Returns (tools, need_rebind, llm_messages, groq_messages, sql_thrash_applied).
    """
    from langchain_core.messages import SystemMessage

    from duckclaw.workers.homeostasis_stuck import loop_post_evaluate_hitl_only_tools

    tools, loop_applied = loop_post_evaluate_hitl_only_tools(
        tools, messages, loop_system_event=loop_system_event
    )
    tools, sql_applied, det = maybe_apply_sql_thrash_tool_guard(tools, messages)
    if det:
        sm = SystemMessage(content=det)
        llm_messages = [sm] + list(llm_messages)
        if groq_messages is not None:
            groq_messages = [sm] + list(groq_messages)
    return tools, bool(loop_applied or sql_applied), llm_messages, groq_messages, sql_applied
