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
    substantive_tools = [
        tool_name
        for tool_name in tools_since
        if tool_name not in {"get_current_time", "await_interval"}
    ]
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


def messages_have_gmail_tools_since(
    messages: list[Any] | None,
    last_human_idx: int,
) -> bool:
    """True when any Gmail MCP tool ran after the last human turn."""
    from langchain_core.messages import ToolMessage

    for message in (messages or [])[max(0, last_human_idx + 1) :]:
        if isinstance(message, ToolMessage) and _is_gmail_mcp_tool_name(
            str(getattr(message, "name", "") or "")
        ):
            return True
    return False


def reply_looks_like_collapsed_stub(text: str) -> bool:
    """Detect model collapse stubs like ``worker_id 1`` or ``5 registros.``."""
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 8:
        return True
    if re.fullmatch(r"[\w.-]+\s+\d+", t):
        return True
    if re.fullmatch(r"\d+\s*registros?(?:\s*\([^)]*\))?\.?", t, re.I):
        return True
    # Stub line + deterministic Gmail snippet dump (no real analysis).
    if re.match(r"^[\w.-]+\s+\d+\s*\n", t) and "Gmail:" in t and len(t) < 600:
        return True
    if t.startswith("Gmail:") and len(t) < 450 and "##" not in t and "**Insight" not in t:
        return True
    return False


def _b64url_decode(data: str) -> str:
    import base64

    raw = (data or "").strip().replace("-", "+").replace("_", "/")
    if not raw:
        return ""
    pad = "=" * (-len(raw) % 4)
    try:
        return base64.b64decode(raw + pad).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _gmail_payload_plain_text(payload: Any, *, depth: int = 0) -> str:
    if not isinstance(payload, dict) or depth > 6:
        return ""
    mime = str(payload.get("mimeType") or "").lower()
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    data = str((body or {}).get("data") or "")
    if data and mime.startswith("text/plain"):
        return _b64url_decode(data)
    parts = payload.get("parts")
    if isinstance(parts, list):
        plain_bits: list[str] = []
        html_bits: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_mime = str(part.get("mimeType") or "").lower()
            nested = _gmail_payload_plain_text(part, depth=depth + 1)
            if not nested:
                continue
            if part_mime.startswith("text/plain"):
                plain_bits.append(nested)
            elif part_mime.startswith("text/html"):
                html_bits.append(nested)
            else:
                plain_bits.append(nested)
        if plain_bits:
            return "\n".join(plain_bits)
        if html_bits:
            # Cheap HTML strip for synthesis evidence.
            html = "\n".join(html_bits)
            return re.sub(r"<[^>]+>", " ", html)
    if data and mime.startswith("text/html"):
        return re.sub(r"<[^>]+>", " ", _b64url_decode(data))
    if data and not mime:
        return _b64url_decode(data)
    return ""


def extract_gmail_evidence_for_synthesis(
    messages: list[Any] | None,
    last_human_idx: int,
    *,
    max_chars: int = 10000,
) -> str:
    """Build plain-text email evidence from Gmail tool results for NL synthesis."""
    from langchain_core.messages import ToolMessage

    chunks: list[str] = []
    for message in (messages or [])[max(0, last_human_idx + 1) :]:
        if not isinstance(message, ToolMessage):
            continue
        name = str(getattr(message, "name", "") or "")
        if not _is_gmail_mcp_tool_name(name):
            continue
        raw = str(getattr(message, "content", "") or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if raw.startswith("{") else None
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if not isinstance(parsed, dict):
            chunks.append(f"### {name}\n{raw[:2000]}")
            continue
        subject = str(parsed.get("subject") or "").strip()
        if not subject:
            payload = parsed.get("payload")
            headers = payload.get("headers") if isinstance(payload, dict) else None
            if isinstance(headers, list):
                for h in headers:
                    if isinstance(h, dict) and str(h.get("name") or "").lower() == "subject":
                        subject = str(h.get("value") or "").strip()
                        break
        snip = str(parsed.get("snippet") or "").strip()
        body = _gmail_payload_plain_text(parsed.get("payload"))
        if not body and isinstance(parsed.get("messages"), list):
            # get_thread: concatenate message bodies
            bodies: list[str] = []
            for msg in parsed["messages"]:
                if isinstance(msg, dict):
                    bit = _gmail_payload_plain_text(msg.get("payload"))
                    if bit:
                        bodies.append(bit)
                    elif msg.get("snippet"):
                        bodies.append(str(msg.get("snippet")))
            body = "\n\n---\n\n".join(bodies)
        parts = [f"### {name}"]
        if subject:
            parts.append(f"Asunto: {subject}")
        if snip:
            parts.append(f"Snippet: {snip}")
        if body:
            parts.append(f"Cuerpo:\n{body.strip()}")
        elif not snip:
            parts.append(raw[:2000])
        chunks.append("\n".join(parts))
    evidence = "\n\n".join(chunks).strip()
    if len(evidence) > max_chars:
        return evidence[:max_chars] + "\n\n…[correo truncado para síntesis]"
    return evidence


def tool_response_needs_egress_repair(
    messages: list[Any] | None,
    incoming: str,
    reply: str,
    *,
    last_human_idx: int,
    repair_enabled: bool = False,
) -> bool:
    """True when an enabled worker returned empty text, raw tool JSON, or a collapse stub."""
    if not repair_enabled:
        return False
    if clock_only_lone_url_no_repair(incoming, messages, last_human_idx=last_human_idx):
        return False
    if reply_is_tool_json_echo(reply or ""):
        return True
    has_tools = False
    has_gmail = messages_have_gmail_tools_since(messages, last_human_idx)
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(message, "name", "") or "")
        for message in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(message, ToolMessage)
    ]
    has_tools = bool(tools_since)
    if not (reply or "").strip():
        return has_tools
    # Gmail turns: model often collapses to ``worker N`` / snippet dump after get_message.
    if has_gmail and reply_looks_like_collapsed_stub(reply):
        return True
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
            # Gmail MCP payloads: prefer subject/snippet over dumping raw JSON.
            if "gmail" in name.lower() or name.endswith(
                ("__get_message", "__get_thread", "__search_threads")
            ):
                if name.endswith("__search_threads") or "search_threads" in name:
                    threads = parsed.get("threads")
                    if isinstance(threads, list):
                        if not threads:
                            return "Gmail: sin hilos para esa búsqueda."
                        snip = ""
                        first = threads[0] if isinstance(threads[0], dict) else {}
                        if isinstance(first, dict):
                            snip = str(first.get("snippet") or "").strip()
                        if snip:
                            return f"Gmail: {len(threads)} hilo(s). {snip[:160]}"
                        return f"Gmail: {len(threads)} hilo(s)."
                subject = str(parsed.get("subject") or "").strip()
                # headers may be a list of {name,value}
                if not subject:
                    payload = parsed.get("payload")
                    headers = payload.get("headers") if isinstance(payload, dict) else None
                    if isinstance(headers, list):
                        for h in headers:
                            if isinstance(h, dict) and str(h.get("name") or "").lower() == "subject":
                                subject = str(h.get("value") or "").strip()
                                break
                    elif isinstance(headers, dict):
                        subject = str(headers.get("Subject") or headers.get("subject") or "").strip()
                snip = str(parsed.get("snippet") or "").strip()
                if subject and snip:
                    return f"Correo «{subject[:120]}»: {snip[:140]}"
                if subject:
                    return f"Correo «{subject[:160]}»."
                if snip:
                    return f"Correo: {snip[:200]}"
                msgs = parsed.get("messages")
                if isinstance(msgs, list) and msgs:
                    return f"Hilo Gmail con {len(msgs)} mensaje(s)."
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


def _is_gmail_mcp_tool_name(tool_name: str) -> bool:
    n = (tool_name or "").strip().lower()
    if not n:
        return False
    if "gmail" in n:
        return True
    return n.endswith(("__search_threads", "__get_message", "__get_thread"))


def _is_local_sql_noise_tool(tool_name: str) -> bool:
    return (tool_name or "").strip() in {"read_sql", "admin_sql", "inspect_schema"}


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

    slice_msgs = messages[max(0, last_human_idx + 1) :]
    has_gmail_tool = any(
        isinstance(m, ToolMessage) and _is_gmail_mcp_tool_name(str(getattr(m, "name", "") or ""))
        for m in slice_msgs
    )

    summaries: list[str] = []
    for message in slice_msgs:
        if not isinstance(message, ToolMessage):
            continue
        tool_name = str(getattr(message, "name", "") or "")
        tool_content = str(getattr(message, "content", "") or "").strip()
        if not tool_content or tool_name == "get_current_time":
            continue
        # Email turns often burn a forced read_sql (SELECT now()); never let that
        # become the user-visible "1 registro (ahora…)." when Gmail already ran.
        if has_gmail_tool and _is_local_sql_noise_tool(tool_name):
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
    gmail_evidence = extract_gmail_evidence_for_synthesis(messages, human_idx)
    tool_parts: list[str] = []
    clock_data = parse_get_current_time_json(reply) or {}
    for message in messages[max(0, human_idx + 1) :]:
        if isinstance(message, ToolMessage):
            tool_name = str(getattr(message, "name", "") or "")
            tool_content = str(getattr(message, "content", "") or "").strip()
            if tool_content and not _is_gmail_mcp_tool_name(tool_name):
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
    if gmail_evidence:
        evidence_parts.append(
            "Correo recuperado via Gmail (usa esto para un análisis completo; "
            "no te limites al snippet):\n" + gmail_evidence
        )
    if tool_parts:
        evidence_parts.append("Resultados de herramientas:\n" + "\n\n".join(tool_parts))
    if (reply or "").strip() and (
        reply_is_tool_json_echo(reply) or reply_looks_like_collapsed_stub(reply)
    ):
        evidence_parts.append(f"Respuesta cruda rechazada:\n{reply.strip()}")
    ask = (incoming or "").strip()
    if gmail_evidence:
        ask = (
            f"{ask}\n\n"
            "Entrega un análisis completo del correo en español: resumen ejecutivo, "
            "insights accionables (viñetas), implicaciones (p. ej. mercado/producto si aplica) "
            "y siguientes pasos. No devuelvas solo el snippet ni stubs numéricos."
        )
    evidence_parts.append(f"Contexto del usuario:\n{ask}")
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
        user_ask=ask,
        raw_evidence=evidence,
        worker_id=worker_id,
        for_admin_console=bool(gmail_evidence),
    )
    synthesized_text = (synthesized or "").strip()
    if (
        synthesized_text
        and not reply_is_tool_json_echo(synthesized_text)
        and not reply_looks_like_collapsed_stub(synthesized_text)
    ):
        return synthesized_text
    deterministic = deterministic_fallback()
    return deterministic if deterministic else reply


__all__ = [
    "clock_only_lone_url_no_repair",
    "deterministic_tool_response_summary",
    "extract_gmail_evidence_for_synthesis",
    "last_human_index",
    "latest_tool_json_since",
    "messages_have_gmail_tools_since",
    "parse_get_current_time_json",
    "post_tools_synthesis_needed",
    "repair_tool_response_egress_reply",
    "reply_is_get_current_time_json_only",
    "reply_is_json_only",
    "reply_is_tool_json_echo",
    "reply_is_tool_label_json_echo",
    "reply_looks_like_collapsed_stub",
    "strip_tool_label_prefix",
    "tool_response_needs_egress_repair",
]
