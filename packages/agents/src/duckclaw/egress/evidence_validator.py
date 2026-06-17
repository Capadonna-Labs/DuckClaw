"""
Transversal answer/evidence validation helpers for worker egress.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

from langchain_core.messages import SystemMessage, ToolMessage

from duckclaw.workers.runtime_policy_helpers import worker_has_runtime_capability

_TICKER_PAT = re.compile(r"\b([A-Z]{1,5})\b")
# Probable quote-like figure: decimal with at least 2 fractional digits or a $ prefix.
_PRICE_PAT = re.compile(r"(?:\$\s*)?(\d{1,6}\.\d{2,6})\b")
_VLM_MARKER = "VLM_CONTEXT"
_EVIDENCE_TOOLS = {"fetch_market_data", "fetch_ib_gateway_ohlcv", "fetch_lake_ohlcv", "read_sql"}
_NUMERIC_VERIFY_STATUSES = frozenset({"verified", "mismatch", "no_evidence"})

VISUAL_EVIDENCE_RETRY_REASON = "missing_tool_evidence_for_vlm_claim"

_VISUAL_EVIDENCE_USER_ERROR = (
    "❌ Regla de Evidencia Única: detecté contexto visual y cifras de mercado sin tool call válido en este turno. "
    "Ejecuta fetch_market_data/fetch_ib_gateway_ohlcv/fetch_lake_ohlcv o read_sql primero y luego recalculo."
)

_VISUAL_EVIDENCE_RETRY_DIRECTIVE = (
    "Contexto VLM con cifras de mercado detectadas en tu borrador. "
    "Ejecuta read_sql o fetch_market_data/fetch_ib_gateway_ohlcv/fetch_lake_ohlcv en este turno "
    "antes de redactar cotizaciones. No cites precios sin un ToolMessage válido de evidencia."
)


def _spec_uses_market_evidence_scope(spec: Any) -> bool:
    return worker_has_runtime_capability(spec, "market_analysis") or worker_has_runtime_capability(
        spec,
        "market_data_bridge",
    )


def spec_requires_bracket_citations(spec: Any) -> bool:
    """Workers with market evidence capabilities must cite figures with ``[tool/symbol]``."""
    return _spec_uses_market_evidence_scope(spec)


_BRACKET_CITATION_RE = re.compile(r"\[[a-z][a-z0-9_]*(?:/[A-Za-z0-9][\w.-]*)?\]", re.IGNORECASE)
_PCT_FIGURE_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%")


def _count_bracket_citations(text: str) -> int:
    return len(_BRACKET_CITATION_RE.findall(text or ""))


def _price_in_non_market_context(text: str, match_start: int, match_end: int, *, window: int = 140) -> bool:
    """
    Avoid treating account/broker balances as current symbol quotes.
    """
    lo = max(0, match_start - window)
    hi = min(len(text), match_end + window)
    chunk = text[lo:hi].lower()
    needles = (
        "interactive brokers",
        "broker:",
        "broker (",
        "gateway",
        "cuentas locales",
        "cuenta broker",
        "bancolombia",
        "nequi",
        "global66",
        "tarjeta cívica",
        "tarjeta civica",
        "nu:",
        "liquidez total",
        "total cuentas",
        "saldo:",
        "usd efectivo",
        "efectivo ($",
        "resumen de cuentas",
        "estado actual de cuentas",
    )
    return any(n in chunk for n in needles)


def _price_in_vix_or_index_context(
    text: str, match_start: int, match_end: int, *, window: int = 120
) -> bool:
    """VIX and broad index levels are not automatically share quotes."""
    lo = max(0, match_start - window)
    hi = min(len(text), match_end + window)
    chunk = text[lo:hi].lower()
    needles = (
        "vix",
        "volatility index",
        "índice vix",
        "indice vix",
        "volatilidad implícita",
        "volatilidad (vix",
        "s&p 500",
        "s&p500",
        "sp500",
        "dow jones",
        "promedio industrial",
        "nasdaq composite",
    )
    return any(n in chunk for n in needles)


def _count_market_figures(text: str) -> int:
    t = text or ""
    prices = sum(
        1
        for m in _PRICE_PAT.finditer(t)
        if not _price_in_non_market_context(t, m.start(), m.end())
        and not _price_in_vix_or_index_context(t, m.start(), m.end())
    )
    pcts = len(_PCT_FIGURE_RE.findall(t))
    return prices + pcts


def _ticker_tool_map_from_messages(messages: list[Any]) -> dict[str, str]:
    """Map uppercase ticker -> tool name from ToolMessages in this turn."""
    out: dict[str, str] = {}
    for m in messages or []:
        if not isinstance(m, ToolMessage):
            continue
        nm = str(getattr(m, "name", "") or "").strip()
        if nm not in _EVIDENCE_TOOLS and nm not in {"tavily_search", "get_current_time"} and "portfolio" not in nm.lower():
            continue
        content = str(getattr(m, "content", "") or "")
        if "error" in content.lower()[:200]:
            continue
        sym = ""
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                raw_t = data.get("ticker") or data.get("symbol")
                if raw_t:
                    sym = str(raw_t).strip().upper()
        except (json.JSONDecodeError, TypeError):
            pass
        if not sym:
            for hit in _TICKER_PAT.finditer(content[:400]):
                cand = hit.group(1)
                if 1 <= len(cand) <= 5:
                    sym = cand
                    break
        if sym and sym not in out:
            out[sym] = nm
    return out


def _inject_bracket_citations(
    text: str,
    *,
    ticker_tool_map: dict[str, str],
    tools_used: set[str],
) -> str:
    """Append ``[tool/ticker]`` after uncited figures when same-turn evidence exists."""
    if not text:
        return text
    out = text
    for sym, tool in sorted(ticker_tool_map.items(), key=lambda kv: -len(kv[0])):
        esc = re.escape(sym)
        out = re.sub(
            rf"(\|\s*{esc}\s*\|\s*)(\$?\d[\d.,]*)(\s*\|)",
            rf"\1\2 [{tool}/{sym}]\3",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            rf"(\b{esc}\b[^\n|{{[\]]{{0,80}}?)(\$?\d{{1,6}}\.\d{{2,6}})(?!\s*\[)",
            rf"\1\2 [{tool}/{sym}]",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            rf"(\b{esc}\b[^\n|{{[\]]{{0,80}}?)([-+]?\d+(?:\.\d+)?%)(?!\s*\[)",
            rf"\1\2 [{tool}/{sym}]",
            out,
            flags=re.IGNORECASE,
        )
    portfolio_tools = sorted(t for t in tools_used if "portfolio" in t.lower())
    if portfolio_tools:
        ptool = portfolio_tools[0]
        tag = f"[{ptool}"
        if tag.lower() not in out.lower():
            for m in _PRICE_PAT.finditer(out):
                if _price_in_non_market_context(out, m.start(), m.end()):
                    continue
                frag = out[m.end() : m.end() + 24]
                if "[" in frag:
                    continue
                out = out[: m.end()] + f" [{ptool}]" + out[m.end() :]
                break
    return out


def bracket_citation_audit(
    reply: str,
    *,
    messages: Optional[list[Any]] = None,
    spec: Any = None,
) -> Tuple[str, Optional[str]]:
    """
    Repair uncited market figures when same-turn tool evidence is available.
    """
    if spec is None or not spec_requires_bracket_citations(spec):
        return reply, None
    text = (reply or "").strip()
    if not text:
        return reply, None

    bracket_n = _count_bracket_citations(text)
    figure_n = _count_market_figures(text)
    if figure_n == 0:
        return reply, None
    if bracket_n >= max(1, figure_n // 2):
        return reply, None

    ticker_map = _ticker_tool_map_from_messages(list(messages or []))
    tools_used: set[str] = set()
    for m in messages or []:
        if isinstance(m, ToolMessage):
            nm = str(getattr(m, "name", "") or "").strip()
            if nm:
                tools_used.add(nm)
    if not ticker_map and not tools_used:
        return reply, None

    repaired = _inject_bracket_citations(
        text,
        ticker_tool_map=ticker_map,
        tools_used=tools_used,
    )
    if repaired == text:
        return reply, None
    return repaired, f"injected_brackets figures={figure_n} before={bracket_n} after={_count_bracket_citations(repaired)}"


def _known_tickers(db: Any) -> set[str]:
    try:
        raw = db.query(
            "SELECT DISTINCT UPPER(ticker) AS t FROM market_data.ohlcv_data LIMIT 500"
        )
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not rows or not isinstance(rows, list):
            return set()
        out: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                t = row.get("t") or row.get("ticker")
                if t:
                    out.add(str(t).strip().upper())
        return out
    except Exception:
        return set()


def market_price_consistency_audit(
    db: Any,
    spec: Any,
    reply: str,
    messages: Optional[list[Any]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Placeholder for DB-backed quote consistency checks.

    The previous implementation depended on a domain-owned OHLCV table. Keeping this
    disabled avoids baking a vertical schema into transversal egress validation.
    """
    _ = (db, spec, messages)
    return reply, None


def _tool_message_satisfies_visual_evidence(m: ToolMessage) -> bool:
    nm = str(getattr(m, "name", "") or "").strip()
    content = str(getattr(m, "content", "") or "")
    low = content.lower()
    if nm in _EVIDENCE_TOOLS and "error" not in low:
        return True
    if nm == "verify_visual_claim":
        if "error" in low:
            return False
        try:
            data = json.loads(content)
            if isinstance(data, dict) and data.get("status") in _NUMERIC_VERIFY_STATUSES:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def visual_evidence_retry_system_message() -> SystemMessage:
    """Internal retry instruction for the worker graph."""
    return SystemMessage(content=_VISUAL_EVIDENCE_RETRY_DIRECTIVE)


def enforce_visual_evidence_rule(
    *,
    incoming: str,
    messages: list[Any],
    reply: str,
    db: Any = None,
    spec: Any = None,
) -> Tuple[str, Optional[str]]:
    """
    Require same-turn tool evidence before quoting visual-context market figures.
    """
    inc = (incoming or "").strip()
    text = (reply or "").strip()
    if not inc or _VLM_MARKER not in inc:
        return reply, None
    if not _PRICE_PAT.search(text):
        return reply, None

    if db is not None and spec is not None and _spec_uses_market_evidence_scope(spec):
        known = _known_tickers(db)
        if not known:
            return reply, None
        mentioned = {m.group(1) for m in _TICKER_PAT.finditer(text) if m.group(1) in known}
        if not mentioned:
            return reply, None

    for m in messages or []:
        if isinstance(m, ToolMessage) and _tool_message_satisfies_visual_evidence(m):
            return reply, None
    return (_VISUAL_EVIDENCE_USER_ERROR, VISUAL_EVIDENCE_RETRY_REASON)


__all__ = [
    "VISUAL_EVIDENCE_RETRY_REASON",
    "bracket_citation_audit",
    "enforce_visual_evidence_rule",
    "market_price_consistency_audit",
    "spec_requires_bracket_citations",
    "visual_evidence_retry_system_message",
]
