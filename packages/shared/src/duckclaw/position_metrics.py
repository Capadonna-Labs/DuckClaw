"""Deterministic position arithmetic — magnitudes only, no LLM.

Convention (confirmed): dist_sl_pct / dist_tp_pct are always non-negative
percentages of remaining distance to each level. ``side`` is inferred from
geometry (long | short | ambiguous).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

_TP_SL_TOOL_NAME = "calculate_tp_sl_distance"
_PNL_TOOL_NAME = "calculate_pnl_contribution"
_DELEV_TOOL_NAME = "calculate_deleveraging_tranche"

POSITION_METRICS_TOOL_NAMES = frozenset(
    {_TP_SL_TOOL_NAME, _PNL_TOOL_NAME, _DELEV_TOOL_NAME}
)

# Prose patterns that claim SL/TP distance percentages without tool evidence.
_SL_TP_PCT_CLAIM_RE = re.compile(
    r"(?:"
    r"(?:dist(?:ancia)?\s*(?:a\s*)?(?:SL|TP)|"
    r"(?:SL|TP)\s*(?:dist(?:ancia)?|a)|"
    r"hacia\s+(?:el\s+)?(?:SL|TP)|"
    r"stop[\s_-]?loss|take[\s_-]?profit|"
    r"dist_sl|dist_tp|"
    r"RR\s*(?:ratio)?|"
    r"risk[\s/-]*reward)"
    r"[^\n%]{0,40}"
    r"[-+]?\d+(?:\.\d+)?\s*%"
    r"|"
    r"[-+]?\d+(?:\.\d+)?\s*%"
    r"[^\n%]{0,40}"
    r"(?:del?\s+)?(?:SL|TP|stop[\s_-]?loss|take[\s_-]?profit|dist_sl|dist_tp)"
    r")",
    re.IGNORECASE,
)

POSITION_METRICS_RETRY_REASON = "missing_tool_evidence_for_tp_sl_distance"

POSITION_METRICS_RETRY_DIRECTIVE = (
    "Cifras de distancia SL/TP o RR detectadas en prosa sin tool call en este turno. "
    "Invoca calculate_tp_sl_distance(price, sl, tp) y copia el JSON tal cual en el reporte. "
    "Prohibido recalcular porcentajes en lenguaje natural."
)

POSITION_METRICS_USER_ERROR = (
    "❌ Regla de métricas de posición: detecté % de distancia SL/TP o RR en el borrador "
    "sin invocar calculate_tp_sl_distance en este turno. "
    "Llama la tool y reporta los valores del JSON sin recalcular."
)


def _is_markdown_table_line(line: str) -> bool:
    """True for GFM table rows and separator lines (| ... | / | --- |)."""
    s = (line or "").strip()
    return s.startswith("|") and s.count("|") >= 2


def strip_tp_sl_pct_claims(text: str) -> str:
    """Remove SL/TP distance / RR percentage claims from prose; keep the rest.

    Preserves markdown table rows/separators: dropping ``| --- |`` breaks GFM
    and the playground renders pipe rows as one paragraph.
    """
    lines: list[str] = []
    for line in (text or "").splitlines():
        # Never mutate or drop GFM table structure.
        if _is_markdown_table_line(line):
            lines.append(line.rstrip())
            continue
        cleaned = _SL_TP_PCT_CLAIM_RE.sub("", line)
        if not cleaned.strip():
            lines.append("")
            continue
        if re.sub(r"[\s·|,:;\-–—]+", "", cleaned):
            lines.append(cleaned.rstrip())
    # Collapse runs of blank lines only (keep single blanks for markdown blocks).
    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            out.append(line)
            continue
        blank_run += 1
        if blank_run <= 2:
            out.append("")
    return "\n".join(out).strip()


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _round4(v: float) -> float:
    return round(v, 4)


def infer_side(price: float, sl: float, tp: float) -> str:
    """Infer long/short from level geometry relative to price."""
    if sl < price < tp:
        return "long"
    if tp < price < sl:
        return "short"
    # Edge: price exactly on a level but other side still ordered.
    if sl < price and tp > price:
        return "long"
    if sl > price and tp < price:
        return "short"
    return "ambiguous"


def calculate_tp_sl_distance(
    price: float | int | str,
    sl: float | int | str,
    tp: float | int | str,
) -> dict[str, Any]:
    """
    Unsigned % distances to SL/TP plus RR.

    Returns magnitudes only (always >= 0). Side is separate.
    """
    p = _finite(price)
    s = _finite(sl)
    t = _finite(tp)
    base: dict[str, Any] = {
        "ok": False,
        "price": p,
        "sl": s,
        "tp": t,
        "side": "ambiguous",
        "dist_sl_pct": None,
        "dist_tp_pct": None,
        "rr_ratio": None,
    }
    if p is None or s is None or t is None:
        base["error"] = "price, sl y tp deben ser números finitos"
        return base
    if p <= 0:
        base["error"] = "price debe ser > 0"
        return base
    if s == t:
        base["error"] = "sl y tp no pueden ser iguales"
        return base

    side = infer_side(p, s, t)
    dist_sl = abs(p - s) / p * 100.0
    dist_tp = abs(t - p) / p * 100.0
    out: dict[str, Any] = {
        "ok": True,
        "price": p,
        "sl": s,
        "tp": t,
        "side": side,
        "dist_sl_pct": _round4(dist_sl),
        "dist_tp_pct": _round4(dist_tp),
        "rr_ratio": _round4(dist_tp / dist_sl) if dist_sl > 0 else None,
    }
    if side == "ambiguous":
        out["ok"] = False
        out["error"] = (
            "geometría ambigua: se esperaba sl < price < tp (long) "
            "o tp < price < sl (short)"
        )
    return out


def calculate_pnl_contribution(
    pnl: float | int | str,
    portfolio_pnl: float | int | str,
) -> dict[str, Any]:
    """Ticker contribution as % of portfolio PnL (signed when portfolio_pnl != 0)."""
    leg = _finite(pnl)
    total = _finite(portfolio_pnl)
    base: dict[str, Any] = {
        "ok": False,
        "pnl": leg,
        "portfolio_pnl": total,
        "contribution_pct": None,
    }
    if leg is None or total is None:
        base["error"] = "pnl y portfolio_pnl deben ser números finitos"
        return base
    if total == 0:
        base["error"] = "portfolio_pnl es 0; contribución indefinida"
        return base
    return {
        "ok": True,
        "pnl": leg,
        "portfolio_pnl": total,
        "contribution_pct": _round4(leg / total * 100.0),
    }


def calculate_deleveraging_tranche(
    current_pct: float | int | str,
    target_pct: float | int | str,
    steps_remaining: float | int | str,
) -> dict[str, Any]:
    """Equal-sized tranche in percentage points toward target exposure."""
    cur = _finite(current_pct)
    tgt = _finite(target_pct)
    steps_f = _finite(steps_remaining)
    base: dict[str, Any] = {
        "ok": False,
        "current_pct": cur,
        "target_pct": tgt,
        "steps_remaining": None,
        "tranche_pct_points": None,
        "gap_pct_points": None,
    }
    if cur is None or tgt is None or steps_f is None:
        base["error"] = "current_pct, target_pct y steps_remaining deben ser números finitos"
        return base
    steps = int(steps_f)
    if steps_f != steps or steps < 1:
        base["error"] = "steps_remaining debe ser un entero >= 1"
        return base
    gap = cur - tgt
    tranche = gap / steps
    return {
        "ok": True,
        "current_pct": cur,
        "target_pct": tgt,
        "steps_remaining": steps,
        "gap_pct_points": _round4(gap),
        "tranche_pct_points": _round4(tranche),
    }


def reply_claims_tp_sl_pct(text: str) -> bool:
    """True if reply prose asserts SL/TP distance or RR percentages."""
    return bool(_SL_TP_PCT_CLAIM_RE.search(text or ""))


def turn_has_tp_sl_tool_evidence(messages: list[Any] | None) -> bool:
    """True if this turn already called calculate_tp_sl_distance successfully."""
    for m in messages or []:
        name = str(getattr(m, "name", "") or "").strip()
        if name != _TP_SL_TOOL_NAME:
            continue
        content = str(getattr(m, "content", "") or "")
        low = content.lower()
        if "error" in low[:200] and '"ok": false' in low.replace(" ", ""):
            continue
        if '"ok":true' in low.replace(" ", "") or '"ok": true' in low:
            return True
        # Non-JSON success still counts if tool ran without obvious error prefix.
        if content.strip() and not low.lstrip().startswith("error"):
            return True
    return False


def enforce_position_metrics_rule(
    *,
    reply: str,
    messages: list[Any] | None,
    enabled: bool,
) -> tuple[str, str | None]:
    """
    Require calculate_tp_sl_distance when reply claims SL/TP % distances.

    Only active when ``enabled`` (skill / homeostasis levels / always-pack tool).
    """
    if not enabled:
        return reply, None
    text = (reply or "").strip()
    if not text or not reply_claims_tp_sl_pct(text):
        return reply, None
    if turn_has_tp_sl_tool_evidence(messages):
        return reply, None
    # Levels from evaluate_homeostasis / tp_sl_monitor let mechanical rewrite
    # replace prose — no LLM retry needed.
    if extract_tp_sl_level_inputs(messages):
        return reply, None
    return POSITION_METRICS_USER_ERROR, POSITION_METRICS_RETRY_REASON


def _message_name(m: Any) -> str:
    return str(getattr(m, "name", "") or "").strip()


def _message_content(m: Any) -> str:
    """Flatten ToolMessage content (str or multimodal list blocks)."""
    content = getattr(m, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
                else:
                    c = block.get("content")
                    if isinstance(c, str):
                        parts.append(c)
        return "".join(parts)
    return str(content)


def _parse_json_blob(content: str) -> Any | None:
    raw = (content or "").strip()
    if not raw:
        return None
    # Drop LLM-context truncation marker before parse attempts.
    if "…[truncado por tamaño]" in raw:
        raw = raw.split("…[truncado por tamaño]", 1)[0]
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    i = raw.find("{")
    j = raw.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(raw[i : j + 1])
        except (json.JSONDecodeError, TypeError):
            return None
    i = raw.find("[")
    j = raw.rfind("]")
    if i >= 0 and j > i:
        try:
            return json.loads(raw[i : j + 1])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


# read_sql / tool JSON: numbers may be bare or JSON strings ("245.0").
_NUM = r'("-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)'
_NULL_OR_NUM = rf'(null|{_NUM})'

# tp_sl_monitor.levels row order (also works after mid-JSON truncation).
_LEVEL_ROW_RE = re.compile(
    rf'\{{\s*"id"\s*:\s*"(?P<id>[^"]*)"\s*,\s*'
    rf'"ticker"\s*:\s*"(?P<ticker>[^"]+)"\s*,\s*'
    rf'"price"\s*:\s*(?P<price>{_NULL_OR_NUM})\s*,\s*'
    rf'"stop_loss"\s*:\s*(?P<sl>{_NUM})\s*,\s*'
    rf'"take_profit"\s*:\s*(?P<tp>{_NUM})',
    re.DOTALL,
)


def _num_from_re(group: str | None) -> float | None:
    if group is None or group == "null":
        return None
    return _finite(group.strip().strip('"'))


def _geom_key(sl: float, tp: float) -> str:
    return f"{round(float(sl), 4)}:{round(float(tp), 4)}"


def _scan_levels_from_truncated_text(text: str) -> list[dict[str, Any]]:
    """Pull level rows even when evaluate_homeostasis JSON was size-truncated."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _LEVEL_ROW_RE.finditer(text or ""):
        price = _num_from_re(m.group("price"))
        sl = _num_from_re(m.group("sl"))
        tp = _num_from_re(m.group("tp"))
        ticker = (m.group("ticker") or "").strip().upper()
        if not ticker or sl is None or tp is None:
            continue
        window = (text or "")[m.start() : m.end() + 80]
        status_m = re.search(r'"status"\s*:\s*"([^"]+)"', window)
        status = (status_m.group(1) if status_m else "ACTIVE").strip().upper()
        if status.endswith("_HIT") or status in {"CLOSED", "RESOLVED", "CANCELLED", "CANCELED"}:
            continue
        key = f"{ticker}:{_geom_key(sl, tp)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "ticker": ticker,
                "price": price,  # may be None — merge later with calculate_tp_sl_distance
                "sl": sl,
                "tp": tp,
                "status": status or "ACTIVE",
                "id": m.group("id") or "",
            }
        )
    # Flexible order: ticker + stop_loss/take_profit only until the next ticker key
    # (avoids stealing SL/TP from the following level in a dense JSON array).
    for m in re.finditer(r'"ticker"\s*:\s*"([A-Za-z0-9.\-]+)"', text or ""):
        ticker = (m.group(1) or "").strip().upper()
        if not ticker:
            continue
        lo = max(0, m.start() - 40)
        rest = (text or "")[m.end() :]
        next_t = re.search(r'"ticker"\s*:\s*"', rest)
        hi = m.end() + (next_t.start() if next_t else min(200, len(rest)))
        window = (text or "")[lo:hi]
        sl_m = re.search(rf'"stop_loss"\s*:\s*{_NUM}', window)
        tp_m = re.search(rf'"take_profit"\s*:\s*{_NUM}', window)
        if not sl_m or not tp_m:
            continue
        sl = _num_from_re(sl_m.group(1))
        tp = _num_from_re(tp_m.group(1))
        if sl is None or tp is None:
            continue
        price_m = re.search(rf'"price"\s*:\s*{_NULL_OR_NUM}', window)
        price = _num_from_re(price_m.group(1)) if price_m else None
        status_m = re.search(r'"status"\s*:\s*"([^"]+)"', window)
        status = (status_m.group(1) if status_m else "ACTIVE").strip().upper()
        if status.endswith("_HIT") or status in {"CLOSED", "RESOLVED", "CANCELLED", "CANCELED"}:
            continue
        key = f"{ticker}:{_geom_key(sl, tp)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "ticker": ticker,
                "price": price,
                "sl": sl,
                "tp": tp,
                "status": status or "ACTIVE",
                "id": "",
            }
        )
    return out


def _coerce_level_row(
    row: dict[str, Any],
    *,
    require_price: bool = True,
) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    raw_price = row.get("price")
    if raw_price is None:
        raw_price = row.get("last")
    if raw_price is None:
        raw_price = row.get("close")
    price = _finite(raw_price)
    sl = _finite(
        row.get("stop_loss")
        if row.get("stop_loss") is not None
        else (row.get("sl") if row.get("sl") is not None else row.get("stop"))
    )
    tp = _finite(
        row.get("take_profit")
        if row.get("take_profit") is not None
        else (row.get("tp") if row.get("tp") is not None else row.get("target"))
    )
    status = str(row.get("status") or "ACTIVE").strip().upper()
    if sl is None or tp is None:
        return None
    if require_price and price is None:
        return None
    if status and status not in {"ACTIVE", "OPEN", "PENDING", ""}:
        # Keep only live levels for distance reporting.
        if status.endswith("_HIT") or status in {"CLOSED", "RESOLVED", "CANCELLED", "CANCELED"}:
            return None
    return {
        "ticker": ticker,  # may be "" for calculate_tp_sl_distance JSON
        "price": price,  # may be None when require_price=False
        "sl": sl,
        "tp": tp,
        "status": status or "ACTIVE",
        "id": str(row.get("id") or ""),
    }


def _levels_from_payload(
    data: Any,
    *,
    allow_anonymous_metrics: bool = False,
    require_price: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if data is None:
        return out
    if isinstance(data, list):
        for row in data:
            coerced = (
                _coerce_level_row(row, require_price=require_price)
                if isinstance(row, dict)
                else None
            )
            if coerced and (coerced["ticker"] or allow_anonymous_metrics):
                out.append(coerced)
        return out
    if not isinstance(data, dict):
        return out

    # Nested monitor/levels first — never short-circuit on top-level price/sl/tp.
    candidates: list[Any] = []
    mon = data.get("tp_sl_monitor")
    if isinstance(mon, dict):
        candidates.append(mon.get("levels"))
    candidates.append(data.get("levels"))
    candidates.append(data.get("tp_sl_levels"))
    for cand in candidates:
        out.extend(
            _levels_from_payload(
                cand,
                allow_anonymous_metrics=False,
                require_price=require_price,
            )
        )
    if out:
        return out

    # calculate_tp_sl_distance single result (no ticker arg on the tool).
    if (
        allow_anonymous_metrics
        and data.get("ok") is True
        and _finite(data.get("price")) is not None
        and _finite(data.get("sl")) is not None
        and _finite(data.get("tp")) is not None
    ):
        coerced = _coerce_level_row(
            {
                "ticker": data.get("ticker") or data.get("symbol") or "",
                "price": data.get("price"),
                "sl": data.get("sl"),
                "tp": data.get("tp"),
                "status": "ACTIVE",
            },
            require_price=True,
        )
        if coerced:
            out.append(coerced)
    return out


def _level_dedupe_key(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or "").strip().upper()
    if ticker and ticker != "?":
        return f"t:{ticker}"
    # ponytail: tool JSON has no ticker — key by geometry so N calls don't collapse to "?"
    return f"p:{row.get('price')}:{row.get('sl')}:{row.get('tp')}"


def _merge_named_with_metrics(
    named: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach tickers from homeostasis levels onto calculate_tp_sl_distance rows via SL/TP."""
    by_geom: dict[str, dict[str, Any]] = {}
    for row in named:
        sl, tp = row.get("sl"), row.get("tp")
        if sl is None or tp is None:
            continue
        g = _geom_key(float(sl), float(tp))
        # First writer wins — later flexible-scan noise must not steal geom→ticker.
        if g not in by_geom:
            by_geom[g] = row

    if not named and not metrics:
        return []
    if named and not metrics:
        # Only keep rows that already have price (can compute distance).
        return [r for r in named if r.get("price") is not None and (r.get("ticker") or "").strip()]

    out: list[dict[str, Any]] = []
    used_geom: set[str] = set()
    for mrow in metrics:
        sl, tp, price = mrow.get("sl"), mrow.get("tp"), mrow.get("price")
        if sl is None or tp is None or price is None:
            continue
        g = _geom_key(float(sl), float(tp))
        nrow = by_geom.get(g)
        ticker = (nrow.get("ticker") if nrow else "") or mrow.get("ticker") or ""
        ticker = str(ticker).strip().upper()
        # Also try match by price+sl+tp against named that already had price.
        if not ticker:
            for nrow2 in named:
                if nrow2.get("price") is None:
                    continue
                if (
                    abs(float(nrow2["price"]) - float(price)) < 1e-6
                    and abs(float(nrow2["sl"]) - float(sl)) < 1e-6
                    and abs(float(nrow2["tp"]) - float(tp)) < 1e-6
                ):
                    ticker = str(nrow2.get("ticker") or "").strip().upper()
                    break
        used_geom.add(g)
        out.append(
            {
                "ticker": ticker,
                "price": float(price),
                "sl": float(sl),
                "tp": float(tp),
                "status": "ACTIVE",
                "id": (nrow.get("id") if nrow else "") or "",
            }
        )

    # Named rows with price that had no matching calculate_* call.
    for nrow in named:
        if nrow.get("price") is None or not (nrow.get("ticker") or "").strip():
            continue
        g = _geom_key(float(nrow["sl"]), float(nrow["tp"]))
        if g in used_geom:
            continue
        out.append(dict(nrow))
    return out


def _price_ticker_hints_from_messages(messages: list[Any] | None) -> dict[float, str]:
    """Map last/close/price → ticker from market/portfolio tool blobs."""
    out: dict[float, str] = {}
    wanted = {
        "fetch_market_data",
        "read_sql",
        "evaluate_homeostasis",
        "evaluate_tp_sl_monitor",
    }
    for m in messages or []:
        name = _message_name(m)
        if name not in wanted:
            continue
        raw = _message_content(m)
        # Pair nearby ticker + numeric price fields.
        for tm in re.finditer(r'"ticker"\s*:\s*"([A-Za-z0-9.\-]+)"', raw):
            ticker = tm.group(1).strip().upper()
            window = raw[tm.start() : tm.start() + 400]
            for pm in re.finditer(
                r'"(?:price|last|close|current_price|avgCost|market_price)"\s*:\s*(-?\d+(?:\.\d+)?)',
                window,
            ):
                px = _finite(pm.group(1))
                if px is None or px <= 0:
                    continue
                out[round(px, 4)] = ticker
        # Portfolio rows sometimes use "symbol"
        for tm in re.finditer(r'"symbol"\s*:\s*"([A-Za-z0-9.\-]+)"', raw):
            ticker = tm.group(1).strip().upper()
            window = raw[tm.start() : tm.start() + 400]
            for pm in re.finditer(
                r'"(?:price|last|close|current_price|avgCost|market_price)"\s*:\s*(-?\d+(?:\.\d+)?)',
                window,
            ):
                px = _finite(pm.group(1))
                if px is None or px <= 0:
                    continue
                out[round(px, 4)] = ticker
    return out


def extract_tp_sl_level_inputs(messages: list[Any] | None) -> list[dict[str, Any]]:
    """
    Collect ACTIVE (price, sl, tp, ticker) from same-turn tool results.

    Prefer evaluate_homeostasis / evaluate_tp_sl_monitor / read_tp_sl_levels
    (including size-truncated JSON via regex scan). Merge calculate_tp_sl_distance
    rows onto named levels by stop_loss/take_profit when tool JSON has no ticker.
    """
    monitor_names = {
        "evaluate_homeostasis",
        "evaluate_tp_sl_monitor",
        "read_tp_sl_levels",
    }
    named: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []

    for m in messages or []:
        name = _message_name(m)
        if name not in monitor_names:
            continue
        raw = _message_content(m)
        payload = _parse_json_blob(raw)
        # Allow null price so we can still recover tickers for merge.
        rows = _levels_from_payload(payload, allow_anonymous_metrics=False, require_price=False)
        scanned = _scan_levels_from_truncated_text(raw)
        # Prefer coerced; extend with scanned not already present.
        have = {
            (r.get("ticker"), _geom_key(float(r["sl"]), float(r["tp"])))
            for r in rows
            if r.get("sl") is not None and r.get("tp") is not None
        }
        for r in scanned:
            k = (r.get("ticker"), _geom_key(float(r["sl"]), float(r["tp"])))
            if k not in have:
                rows.append(r)
                have.add(k)
        named.extend(rows)

    # Also scan any message for level-shaped ticker/sl/tp (read_sql rows, odd wrappers).
    if not named:
        for m in messages or []:
            raw = _message_content(m)
            if "stop_loss" not in raw or "ticker" not in raw:
                continue
            payload = _parse_json_blob(raw)
            rows = _levels_from_payload(
                payload, allow_anonymous_metrics=False, require_price=False
            )
            scanned = _scan_levels_from_truncated_text(raw)
            named.extend(rows + scanned)

    for m in messages or []:
        name = _message_name(m)
        if name != _TP_SL_TOOL_NAME:
            continue
        raw = _message_content(m)
        payload = _parse_json_blob(raw)
        rows = _levels_from_payload(payload, allow_anonymous_metrics=True, require_price=True)
        metrics.extend(rows)

    merged = _merge_named_with_metrics(named, metrics)
    # Tertiary: map calculate price → ticker via fetch_market_data / portfolio hints.
    if merged and any(not (r.get("ticker") or "").strip() for r in merged):
        hints = _price_ticker_hints_from_messages(messages)
        for r in merged:
            if (r.get("ticker") or "").strip():
                continue
            px = r.get("price")
            if px is None:
                continue
            hit = hints.get(round(float(px), 4))
            if hit:
                r["ticker"] = hit

    # Fallback: named-only or metrics-only (deduped).
    if not merged:
        by_key: dict[str, dict[str, Any]] = {}
        for row in named + metrics:
            if row.get("price") is None:
                continue
            by_key[_level_dedupe_key(row)] = row
        merged = list(by_key.values())
        if merged and any(not (r.get("ticker") or "").strip() for r in merged):
            hints = _price_ticker_hints_from_messages(messages)
            for r in merged:
                if (r.get("ticker") or "").strip():
                    continue
                px = r.get("price")
                if px is None:
                    continue
                hit = hints.get(round(float(px), 4))
                if hit:
                    r["ticker"] = hit

    # Dedup by ticker (or geometry for anonymous leftovers).
    deduped: dict[str, dict[str, Any]] = {}
    for row in merged:
        t = (row.get("ticker") or "").strip().upper()
        key = f"t:{t}" if t and t != "?" else _level_dedupe_key(row)
        prev = deduped.get(key)
        if prev is None:
            deduped[key] = row
            continue
        if prev.get("price") is None and row.get("price") is not None:
            deduped[key] = row
        elif not (prev.get("ticker") or "").strip() and t:
            deduped[key] = row
    return list(deduped.values())


def build_canonical_tp_sl_section(levels: list[dict[str, Any]]) -> str:
    """Deterministic TP/SL block — magnitudes from calculate_tp_sl_distance."""
    lines: list[str] = [
        "## Distancia TP/SL (determinística)",
        "",
        "| Ticker | Side | Dist SL % | Dist TP % | RR |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    n_ok = 0
    ordered = sorted(
        levels,
        key=lambda r: (str(r.get("ticker") or "\uffff").upper(), str(r.get("id") or "")),
    )
    for row in ordered:
        metrics = calculate_tp_sl_distance(row["price"], row["sl"], row["tp"])
        if not metrics.get("ok"):
            continue
        n_ok += 1
        ticker = (row.get("ticker") or "").strip().upper() or "?"
        lines.append(
            "| {ticker} | {side} | {sl} | {tp} | {rr} |".format(
                ticker=ticker,
                side=metrics.get("side") or "?",
                sl=metrics.get("dist_sl_pct"),
                tp=metrics.get("dist_tp_pct"),
                rr=metrics.get("rr_ratio") if metrics.get("rr_ratio") is not None else "—",
            )
        )
    if n_ok == 0:
        return ""
    lines.append("")
    lines.append(
        "_Fuente: calculate_tp_sl_distance sobre niveles ACTIVE del turno "
        "(no recalcular signos en prosa)._"
    )
    return "\n".join(lines)


def apply_deterministic_tp_sl_rewrite(
    reply: str,
    messages: list[Any] | None,
) -> tuple[str, dict[str, Any]]:
    """
    Mechanical pipeline: strip LLM % SL/TP claims and append canonical distances.

    Does not depend on the model choosing to call the tool. Uses levels already
    present in evaluate_homeostasis / tp_sl_monitor (or prior tool JSON).
    """
    levels = extract_tp_sl_level_inputs(messages)
    meta: dict[str, Any] = {
        "levels_found": len(levels),
        "tickers": [r.get("ticker") or "?" for r in levels],
        "claims_before": reply_claims_tp_sl_pct(reply or ""),
        "rewrote": False,
        "section_rows": 0,
    }
    if not levels:
        return reply, meta
    section = build_canonical_tp_sl_section(levels)
    if not section:
        return reply, meta
    cleaned = strip_tp_sl_pct_claims(reply or "")
    # Avoid duplicating section on graph retries.
    marker = "## Distancia TP/SL (determinística)"
    if marker in cleaned:
        head = cleaned.split(marker, 1)[0].rstrip()
        cleaned = head
    text = (cleaned + "\n\n" + section).strip() if cleaned else section
    meta["rewrote"] = True
    meta["section_rows"] = max(0, section.count("\n| ") - 1)
    meta["claims_after"] = reply_claims_tp_sl_pct(text)
    return text, meta


__all__ = [
    "POSITION_METRICS_RETRY_DIRECTIVE",
    "POSITION_METRICS_RETRY_REASON",
    "POSITION_METRICS_TOOL_NAMES",
    "POSITION_METRICS_USER_ERROR",
    "apply_deterministic_tp_sl_rewrite",
    "build_canonical_tp_sl_section",
    "calculate_deleveraging_tranche",
    "calculate_pnl_contribution",
    "calculate_tp_sl_distance",
    "enforce_position_metrics_rule",
    "extract_tp_sl_level_inputs",
    "infer_side",
    "reply_claims_tp_sl_pct",
    "strip_tp_sl_pct_claims",
    "turn_has_tp_sl_tool_evidence",
]
