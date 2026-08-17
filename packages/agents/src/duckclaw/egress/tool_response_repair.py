"""Transversal egress repair helpers for raw tool responses and JSON echoes."""

from __future__ import annotations

import json
import re
from typing import Any

_LONE_HTTP_URL_ONLY_LINE = re.compile(r"^\s*https?://[^\s]+\s*$", re.I)
_TOOL_LABEL_JSON_PREFIX = re.compile(r"^[a-z][a-z0-9_]*:\s*[\[{]", re.IGNORECASE)
_TOOL_LABEL_PREFIX = re.compile(r"^[a-z][a-z0-9_]*:\s*", re.IGNORECASE)


def parse_get_current_time_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not {"iso_8601", "day_of_week", "date", "time"}.issubset(set(data.keys())):
        return None
    return data


def reply_is_get_current_time_json_only(text: str) -> bool:
    return parse_get_current_time_json(text or "") is not None


def strip_tool_label_prefix(text: str) -> str:
    """Remove prefixes like ``read_sql:`` when the model echoes raw tool JSON."""
    raw = (text or "").strip()
    match = _TOOL_LABEL_PREFIX.match(raw)
    if match:
        return raw[match.end() :].strip()
    return raw


def reply_is_json_only(text: str) -> bool:
    """True when the full reply is a JSON object or array, not prose."""
    raw = strip_tool_label_prefix(text or "")
    if not raw.startswith(("{", "[")):
        return False
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, (dict, list))


def reply_is_tool_label_json_echo(text: str) -> bool:
    """Echo like ``tool_name: [{...`` without user-visible synthesis."""
    raw = (text or "").strip()
    return bool(_TOOL_LABEL_JSON_PREFIX.match(raw))


def reply_is_tool_json_echo(text: str) -> bool:
    from duckclaw.integrations.llm_providers import reply_contains_dsml_tool_markup

    return (
        reply_is_get_current_time_json_only(text)
        or reply_is_tool_label_json_echo(text)
        or reply_is_json_only(text)
        or reply_contains_dsml_tool_markup(text)
    )


def _incoming_has_vlm_context(text: str) -> bool:
    low = (text or "").lower()
    return "[vlm_context" in low or "contexto visual adjunto:" in low


def _incoming_is_lone_http_url(text: str) -> bool:
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((text or "").strip()))


def post_tools_synthesis_needed(
    messages: list[Any] | None,
    incoming: str,
    *,
    last_human_idx: int,
    already_has_tool_result: bool,
) -> bool:
    """Any substantive tool after visual or URL context should be synthesized to prose."""
    if not already_has_tool_result:
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(message, "name", "") or "")
        for message in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(message, ToolMessage)
    ]
    if not tools_since:
        return False
    substantive_tools = [tool_name for tool_name in tools_since if tool_name != "get_current_time"]
    if substantive_tools:
        return True
    return _incoming_has_vlm_context(incoming)


def clock_only_lone_url_no_repair(
    incoming: str,
    messages: list[Any] | None,
    *,
    last_human_idx: int,
) -> bool:
    """Lone URL plus only ``get_current_time`` should not trigger synthesis."""
    if not _incoming_is_lone_http_url(incoming) or _incoming_has_vlm_context(incoming):
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(message, "name", "") or "")
        for message in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(message, ToolMessage)
    ]
    return tools_since == ["get_current_time"]


def tool_response_needs_egress_repair(
    messages: list[Any] | None,
    incoming: str,
    reply: str,
    *,
    last_human_idx: int,
    repair_enabled: bool = False,
) -> bool:
    """True when an enabled worker returned empty text or raw tool JSON."""
    if not repair_enabled:
        return False
    if clock_only_lone_url_no_repair(incoming, messages, last_human_idx=last_human_idx):
        return False
    if reply_is_tool_json_echo(reply or ""):
        return True
    if not (reply or "").strip():
        from langchain_core.messages import ToolMessage

        tools_since = [
            str(getattr(message, "name", "") or "")
            for message in (messages or [])[max(0, last_human_idx + 1) :]
            if isinstance(message, ToolMessage)
        ]
        return bool(tools_since)
    return False


def _parse_json_preview(raw: str) -> str | None:
    stripped = strip_tool_label_prefix(raw or "")
    if not stripped or not stripped.startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("preview"), str):
        preview = parsed["preview"].strip()
        if preview:
            return preview[:240]
    if isinstance(parsed, (dict, list)):
        compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return compact[:240]
    return None


def _humanize_tool_line(tool_name: str, tool_content: str) -> str:
    """Una línea legible por tool; evita volcar JSON crudo al usuario."""
    stripped = strip_tool_label_prefix(tool_content or "").strip()
    if not stripped:
        return ""
    name = (tool_name or "").strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            err_txt = str(parsed.get("error") or "").strip()
            if err_txt:
                return f"No se pudo completar: {err_txt[:200]}"
            if name in ("evaluate_homeostasis", "assess_crons_alignment"):
                aligned = parsed.get("aligned")
                if aligned is None:
                    aligned = parsed.get("metrics_aligned")
                achieved = parsed.get("homeostasis_achieved")
                goals = parsed.get("goals_count")
                mis = parsed.get("misaligned_count")
                parts: list[str] = []
                if achieved is True:
                    parts.append("Homeostasis métricas OK")
                elif achieved is False:
                    parts.append("Homeostasis con desviaciones")
                if aligned is True:
                    parts.append("alineado con /goals")
                elif aligned is False:
                    parts.append("desalineado vs /goals")
                if mis is not None:
                    parts.append(f"desvíos={mis}")
                if goals is not None:
                    parts.append(f"metas={goals}")
                if parts:
                    return "; ".join(parts) + "."
            status = str(parsed.get("status") or "").strip().lower()
            if status in ("success", "ok"):
                label = (
                    str(parsed.get("item") or parsed.get("name") or parsed.get("title") or "").strip()
                )
                if label:
                    return f"Operación completada ({label})."
                # Generic success without label: omit (avoid useless "Operación completada.")
                return ""
            preview = parsed.get("preview")
            if isinstance(preview, str) and preview.strip():
                return preview.strip()[:220]
    if stripped.startswith("["):
        try:
            rows = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            rows = None
        if isinstance(rows, list):
            if not rows:
                return "Sin registros en el resultado."
            if len(rows) == 1 and isinstance(rows[0], dict):
                keys = list(rows[0].keys())[:4]
                return f"1 registro ({', '.join(keys)}…)."
            return f"{len(rows)} registros."
    first_line = stripped.split("\n", 1)[0].strip()
    if first_line and not first_line.startswith(("{", "[")):
        return first_line[:220]
    preview = _parse_json_preview(tool_content)
    if preview and not preview.startswith(("{", "[")):
        return preview[:220]
    return ""


def deterministic_tool_response_summary(
    messages: list[Any],
    last_human_idx: int,
    worker_id: str,
    incoming: str,
    *,
    worker_display_name: str | None = None,
) -> str:
    """Brief user-visible summary from ToolMessages, without a second LLM call."""
    from langchain_core.messages import ToolMessage

    _ = incoming
    brand = (worker_display_name or worker_id or "Worker").strip() or "Worker"
    clock_data = latest_tool_json_since(messages, last_human_idx, "get_current_time") or {}
    header = ""
    if clock_data:
        day = str(clock_data.get("day_of_week") or clock_data.get("date") or "").strip()
        time_text = str(clock_data.get("time") or "")[:5]
        header = f"{brand} · {day} {time_text} COT".strip()

    summaries: list[str] = []
    for message in messages[max(0, last_human_idx + 1) :]:
        if not isinstance(message, ToolMessage):
            continue
        tool_name = str(getattr(message, "name", "") or "")
        tool_content = str(getattr(message, "content", "") or "").strip()
        if not tool_content or tool_name == "get_current_time":
            continue
        line = _humanize_tool_line(tool_name, tool_content)
        if line:
            summaries.append(line)
        if len(summaries) >= 6:
            break

    if not summaries:
        return ""
    body = " ".join(summaries)
    if not body.endswith("."):
        body += "."
    if header:
        return f"{header}\n\n{body}"
    return body


def last_human_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index
    return -1


def latest_tool_json_since(messages: list[Any], from_idx: int, tool_name: str) -> dict[str, Any]:
    from langchain_core.messages import ToolMessage

    for message in reversed(messages[max(0, from_idx + 1) :]):
        if not isinstance(message, ToolMessage) or str(getattr(message, "name", "") or "") != tool_name:
            continue
        try:
            raw = str(getattr(message, "content", "") or "")
            data = json.loads(raw) if raw.strip().startswith("{") else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def repair_tool_response_egress_reply(
    llm: Any,
    spec: Any,
    incoming: str,
    reply: str,
    messages: list[Any],
    *,
    skip_llm_synthesis: bool = False,
    worker_display_name: str | None = None,
) -> str:
    """Fallback synthesis when enabled workers return empty text or raw tool JSON."""
    from duckclaw.egress.user_reply_nl_synthesis import synthesize_user_visible_reply
    from langchain_core.messages import ToolMessage

    human_idx = last_human_index(messages)
    tool_parts: list[str] = []
    clock_data = parse_get_current_time_json(reply) or {}
    for message in messages[max(0, human_idx + 1) :]:
        if isinstance(message, ToolMessage):
            tool_name = str(getattr(message, "name", "") or "")
            tool_content = str(getattr(message, "content", "") or "").strip()
            if tool_content:
                tool_parts.append(f"### {tool_name}\n{tool_content}")
            if tool_name == "get_current_time" and not clock_data:
                clock_data = latest_tool_json_since(messages, human_idx, "get_current_time") or {}

    header = ""
    if clock_data:
        day = str(clock_data.get("day_of_week") or clock_data.get("date") or "").strip()
        time_text = str(clock_data.get("time") or "")[:5]
        brand = (
            worker_display_name
            or str(getattr(spec, "name", None) or "")
            or str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")
            or "Worker"
        ).strip()
        header = f"{brand} · {day} {time_text} COT".strip()

    evidence_parts: list[str] = []
    if header:
        evidence_parts.append(header)
    if tool_parts:
        evidence_parts.append("Resultados de herramientas:\n" + "\n\n".join(tool_parts))
    if (reply or "").strip() and reply_is_tool_json_echo(reply):
        evidence_parts.append(f"Respuesta cruda rechazada:\n{reply.strip()}")
    evidence_parts.append(f"Contexto del usuario:\n{(incoming or '').strip()}")
    evidence = "\n\n".join(evidence_parts)

    worker_id = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    logical_id = str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")

    def deterministic_fallback() -> str:
        return deterministic_tool_response_summary(
            messages,
            human_idx,
            logical_id,
            incoming,
            worker_display_name=worker_display_name or str(getattr(spec, "name", None) or ""),
        )

    if skip_llm_synthesis or llm is None:
        deterministic = deterministic_fallback()
        return deterministic if deterministic else reply
    synthesized = synthesize_user_visible_reply(
        llm,
        user_ask=(incoming or "").strip(),
        raw_evidence=evidence,
        worker_id=worker_id,
    )
    synthesized_text = (synthesized or "").strip()
    if synthesized_text and not reply_is_tool_json_echo(synthesized_text):
        return synthesized_text
    deterministic = deterministic_fallback()
    return deterministic if deterministic else reply


__all__ = [
    "clock_only_lone_url_no_repair",
    "deterministic_tool_response_summary",
    "last_human_index",
    "latest_tool_json_since",
    "parse_get_current_time_json",
    "post_tools_synthesis_needed",
    "repair_tool_response_egress_reply",
    "reply_is_get_current_time_json_only",
    "reply_is_json_only",
    "reply_is_tool_json_echo",
    "reply_is_tool_label_json_echo",
    "strip_tool_label_prefix",
    "tool_response_needs_egress_repair",
]
