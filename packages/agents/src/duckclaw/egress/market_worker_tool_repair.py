"""Market-worker egress repair for tool echoes and empty replies."""

from __future__ import annotations

import json
import re
from typing import Any

_LONE_HTTP_URL_ONLY_LINE = re.compile(r"^\s*https?://[^\s]+\s*$", re.I)

_QUANT_EGRESS_SYNTHESIS_TOOLS = frozenset(
    {
        "tavily_search",
        "run_browser_sandbox",
        "reddit_get_post",
        "fetch_market_data",
        "read_sql",
        "get_ibkr_portfolio",
        "inspect_macro_pgq",
        "inspect_schema",
    }
)


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


def reply_is_fetch_market_data_json_only(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return data.get("status") == "ok" and isinstance(data.get("ticker"), str)


def strip_tool_label_prefix(text: str) -> str:
    """Remove prefixes like ``read_sql:`` when the model echoes raw tool JSON."""
    raw = (text or "").strip()
    m = re.match(r"^[a-z][a-z0-9_]*:\s*", raw, re.IGNORECASE)
    if m:
        return raw[m.end() :].strip()
    return raw


def _looks_like_finanz_ledger_json_rows(data: list[Any]) -> bool:
    if not data or not isinstance(data[0], dict):
        return False
    keys = set(data[0].keys())
    if "timestamp" in keys and "close" in keys:
        return True
    if {"id", "amount"} <= keys or {"description", "creditor"} <= keys:
        return True
    if {"balance", "currency"} <= keys or {"name", "balance"} <= keys:
        return True
    return False


def reply_is_read_sql_json_only(text: str) -> bool:
    """True when egress is a raw read_sql JSON array, not prose."""
    raw = strip_tool_label_prefix(text or "")
    if not raw.startswith("["):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, list) or not data:
        return False
    return _looks_like_finanz_ledger_json_rows(data)


def reply_is_tool_label_json_echo(text: str) -> bool:
    """Echo like ``tool_name: [{...`` without synthesis."""
    raw = (text or "").strip()
    return bool(re.match(r"^[a-z][a-z0-9_]*:\s*[\[{]", raw, re.IGNORECASE))


def reply_is_market_tool_json_echo(text: str) -> bool:
    from duckclaw.integrations.llm_providers import reply_contains_dsml_tool_markup

    return (
        reply_is_get_current_time_json_only(text)
        or reply_is_fetch_market_data_json_only(text)
        or reply_is_read_sql_json_only(text)
        or reply_is_tool_label_json_echo(text)
        or reply_contains_dsml_tool_markup(text)
    )


def _incoming_has_vlm_context(text: str) -> bool:
    low = (text or "").lower()
    return "[vlm_context" in low or "contexto visual adjunto:" in low


def _incoming_is_lone_http_url(text: str) -> bool:
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((text or "").strip()))


def quant_vlm_post_tools_synthesis(
    messages: list[Any] | None,
    incoming: str,
    *,
    last_human_idx: int,
    already_has_tool_result: bool,
) -> bool:
    """Any substantive tool after VLM/URL should be synthesized to prose."""
    if not already_has_tool_result:
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(m, "name", "") or "")
        for m in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(m, ToolMessage)
    ]
    if not tools_since:
        return False
    substantive = [t for t in tools_since if t != "get_current_time"]
    if substantive:
        return True
    has_vlm = _incoming_has_vlm_context(incoming)
    has_lone_url = _incoming_is_lone_http_url(incoming)
    if not (has_vlm or has_lone_url):
        return False
    if has_lone_url and not has_vlm:
        return any(t in _QUANT_EGRESS_SYNTHESIS_TOOLS for t in tools_since)
    return True


def market_worker_gct_only_lone_url_no_repair(
    incoming: str,
    messages: list[Any] | None,
    *,
    last_human_idx: int,
) -> bool:
    """Lone URL + only get_current_time: no synthesis or egress repair."""
    if not _incoming_is_lone_http_url(incoming) or _incoming_has_vlm_context(incoming):
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(m, "name", "") or "")
        for m in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(m, ToolMessage)
    ]
    return tools_since == ["get_current_time"]


def market_worker_needs_egress_repair(
    messages: list[Any] | None,
    incoming: str,
    reply: str,
    *,
    last_human_idx: int,
    worker_id: str | None,
    is_market_worker: bool = False,
) -> bool:
    """Finanz/Quant repair for empty replies or raw JSON echoes."""
    _ = worker_id
    if not is_market_worker:
        return False
    if market_worker_gct_only_lone_url_no_repair(
        incoming, messages, last_human_idx=last_human_idx
    ):
        return False
    if reply_is_market_tool_json_echo(reply or ""):
        return True
    if not (reply or "").strip():
        from langchain_core.messages import ToolMessage

        tools_since = [
            str(getattr(m, "name", "") or "")
            for m in (messages or [])[max(0, last_human_idx + 1) :]
            if isinstance(m, ToolMessage)
        ]
        return bool(tools_since)
    return False


def _parse_read_sql_tool_rows(raw: str) -> list[dict] | None:
    """Parse read_sql ToolMessage: JSON array, ``deudas_filas`` wrapper, or ``preview``."""
    stripped = strip_tool_label_prefix(raw or "")
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, list):
        rows = [r for r in parsed if isinstance(r, dict)]
        return rows or None
    if isinstance(parsed, dict):
        filas = parsed.get("deudas_filas")
        if isinstance(filas, list):
            rows = [r for r in filas if isinstance(r, dict)]
            return rows or None
        preview = parsed.get("preview")
        if isinstance(preview, str) and preview.strip():
            return _parse_read_sql_tool_rows(preview)
    return None


def _format_finanz_deudas_rows_prose(rows: list[dict]) -> str | None:
    """NL summary for Finanz read_sql debt or account rows."""
    if not rows or not isinstance(rows[0], dict):
        return None
    keys = set(rows[0].keys())
    if {"description", "creditor", "amount"} <= keys or {"id", "amount"} <= keys:
        lines: list[str] = []
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            total += amt
            desc = str(row.get("description") or row.get("id") or "?").strip()
            cred = str(row.get("creditor") or "").strip()
            due = str(row.get("due_date") or "")[:10]
            chunk = f"- {desc}: ${amt:,.0f}"
            if cred:
                chunk += f" ({cred})"
            if due:
                chunk += f", vence {due}"
            lines.append(chunk)
        if lines:
            return f"Deudas ({len(lines)} filas), total ${total:,.0f} COP:\n" + "\n".join(lines)
        return None
    if {"balance", "currency"} <= keys or {"name", "balance"} <= keys:
        lines = []
        totals: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                bal = float(row.get("balance") or 0)
            except (TypeError, ValueError):
                bal = 0.0
            cur = str(row.get("currency") or "COP").strip() or "COP"
            totals[cur] = totals.get(cur, 0.0) + bal
            nm = str(row.get("name") or row.get("id") or "?").strip()
            lines.append(f"- {nm}: ${bal:,.0f} {cur}")
        if lines:
            sub = ", ".join(f"${v:,.0f} {k}" for k, v in sorted(totals.items()))
            return f"Cuentas ({len(lines)}):\n" + "\n".join(lines) + f"\nTotal: {sub}"
    return None


def deterministic_market_worker_tool_summary(
    messages: list[Any],
    last_human_idx: int,
    worker_id: str,
    incoming: str,
    *,
    worker_display_name: str | None = None,
) -> str:
    """Brief NL summary from ToolMessages, without a second LLM call."""
    from langchain_core.messages import ToolMessage

    _ = incoming
    brand = (worker_display_name or worker_id or "Worker").strip() or "Worker"
    gct_data = quant_latest_tool_json_since(messages, last_human_idx, "get_current_time") or {}
    hdr = ""
    if gct_data:
        day = str(gct_data.get("day_of_week") or gct_data.get("date") or "").strip()
        tm = str(gct_data.get("time") or "")[:5]
        hdr = f"{brand} · {day} {tm} COT".strip()

    summaries: list[str] = []
    for m in messages[max(0, last_human_idx + 1) :]:
        if not isinstance(m, ToolMessage):
            continue
        tn = str(getattr(m, "name", "") or "")
        tc = str(getattr(m, "content", "") or "").strip()
        if not tc or tn == "get_current_time":
            continue
        if tn in ("fetch_ib_gateway_ohlcv", "fetch_market_data", "fetch_lake_ohlcv"):
            try:
                d = json.loads(tc)
            except (json.JSONDecodeError, TypeError):
                d = None
            if isinstance(d, dict):
                if d.get("error"):
                    tkr = str(d.get("ticker") or "?")
                    err = str(d.get("message") or d.get("error") or "error")
                    summaries.append(f"{tkr}: {err}")
                elif d.get("status") == "ok":
                    tkr = str(d.get("ticker") or "?")
                    rows = d.get("rows_upserted") or d.get("bar_count") or d.get("bars_received")
                    tf = str(d.get("timeframe") or "").strip()
                    lc = d.get("last_close")
                    chunk = tkr
                    if tf:
                        chunk += f" ({tf})"
                    if rows is not None:
                        chunk += f": {rows} velas"
                    if lc is not None:
                        try:
                            chunk += f", último cierre ${float(lc):,.2f}"
                        except (TypeError, ValueError):
                            pass
                    summaries.append(chunk)
                continue
        if tn == "get_ibkr_portfolio":
            m_total = re.search(r"Valor total:\s*\$([0-9,]+(?:\.[0-9]+)?)", tc)
            m_pos = re.search(r"Posiciones:\s*([0-9]+)", tc)
            if m_total:
                chunk = f"Portfolio IBKR ${m_total.group(1)}"
                if m_pos:
                    chunk += f", {m_pos.group(1)} posiciones"
                summaries.append(chunk)
            else:
                summaries.append("Portfolio IBKR consultado.")
            continue
        if tn == "read_sql":
            rows = _parse_read_sql_tool_rows(tc)
            if rows:
                prose = _format_finanz_deudas_rows_prose(rows)
                if prose:
                    summaries.append(prose)
                    continue
        preview = tc.split("\n", 1)[0].strip()[:120]
        if preview:
            summaries.append(f"{tn}: {preview}")

    if not summaries:
        return ""
    body = ". ".join(summaries)
    if not body.endswith("."):
        body += "."
    if hdr:
        return f"{hdr}\n\n{body}"
    return body


def quant_last_human_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return -1


def quant_latest_tool_json_since(messages: list[Any], from_idx: int, tool_name: str) -> dict[str, Any]:
    from langchain_core.messages import ToolMessage

    for m in reversed(messages[max(0, from_idx + 1) :]):
        if not isinstance(m, ToolMessage) or str(getattr(m, "name", "") or "") != tool_name:
            continue
        try:
            raw = str(getattr(m, "content", "") or "")
            data = json.loads(raw) if raw.strip().startswith("{") else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def repair_market_worker_tool_egress_reply(
    llm: Any,
    spec: Any,
    incoming: str,
    reply: str,
    messages: list[Any],
    *,
    skip_llm_synthesis: bool = False,
    worker_display_name: str | None = None,
) -> str:
    """Fallback synthesis when market workers return empty text or raw tool JSON."""
    from duckclaw.egress.user_reply_nl_synthesis import synthesize_user_visible_reply
    from langchain_core.messages import ToolMessage

    lh = quant_last_human_index(messages)
    tool_parts: list[str] = []
    gct_data = parse_get_current_time_json(reply) or {}
    for m in messages[max(0, lh + 1) :]:
        if isinstance(m, ToolMessage):
            tn = str(getattr(m, "name", "") or "")
            tc = str(getattr(m, "content", "") or "").strip()
            if tc:
                tool_parts.append(f"### {tn}\n{tc}")
            if tn == "get_current_time" and not gct_data:
                gct_data = quant_latest_tool_json_since(messages, lh, "get_current_time") or {}

    hdr = ""
    if gct_data:
        day = str(gct_data.get("day_of_week") or gct_data.get("date") or "").strip()
        tm = str(gct_data.get("time") or "")[:5]
        brand = (
            worker_display_name
            or str(getattr(spec, "name", None) or "")
            or str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")
            or "Worker"
        ).strip()
        hdr = f"{brand} · {day} {tm} COT".strip()

    evidence_parts: list[str] = []
    if hdr:
        evidence_parts.append(hdr)
    if tool_parts:
        evidence_parts.append("Resultados de herramientas:\n" + "\n\n".join(tool_parts))
    if (reply or "").strip() and reply_is_market_tool_json_echo(reply):
        evidence_parts.append(f"Respuesta cruda rechazada:\n{reply.strip()}")
    evidence_parts.append(f"Contexto del usuario:\n{(incoming or '').strip()}")
    evidence = "\n\n".join(evidence_parts)

    wid = str(getattr(spec, "worker_id", "") or "").strip() or "market_worker"
    _lh = quant_last_human_index(messages)
    _lid = str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")

    def _deterministic_fallback() -> str:
        return deterministic_market_worker_tool_summary(
            messages,
            _lh,
            _lid,
            incoming,
            worker_display_name=worker_display_name or str(getattr(spec, "name", None) or ""),
        )

    if skip_llm_synthesis:
        det = _deterministic_fallback()
        return det if det else reply
    if llm is None:
        det = _deterministic_fallback()
        return det if det else reply
    syn = synthesize_user_visible_reply(
        llm,
        user_ask=(incoming or "").strip(),
        raw_evidence=evidence,
        worker_id=wid,
    )
    syn_st = (syn or "").strip()
    if syn_st and not reply_is_market_tool_json_echo(syn_st):
        return syn_st
    det = _deterministic_fallback()
    return det if det else reply


def repair_quant_gct_json_echo_reply(
    llm: Any,
    spec: Any,
    incoming: str,
    reply: str,
    messages: list[Any],
) -> str:
    """Compatibility wrapper: get_current_time JSON echo is one market egress case."""
    return repair_market_worker_tool_egress_reply(llm, spec, incoming, reply, messages)
