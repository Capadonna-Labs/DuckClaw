"""Block broker market-entry tools when the intent is a protective OCA/BRACKET.

Error #2 (XLU): ``signal_type=BRACKET`` was POSTed to the IBKR execute hook,
which coerced unknown types to ``ENTRY`` and market-bought. The durable fix
lives in Capadonna ``broker_execute_signal`` + ``signal_execution_bridge``;
this guard is a belt-and-suspenders stop in ``tools_node`` before invoke.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

_log = logging.getLogger(__name__)

# Tools that size/send market orders via the Capadonna IBKR execute hook.
_MARKET_ENTRY_BROKER_TOOLS = frozenset(
    {
        "execute_approved_signal",
        "execute_broker_signals_batch",
        "run_quant_signal_cycle",
    }
)


def _args_blob(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, dict):
        try:
            return json.dumps(args, ensure_ascii=False, default=str)
        except Exception:
            return str(args)
    return str(args)


def _signal_type_from_args(args: Any) -> str | None:
    if not isinstance(args, dict):
        return None
    for key in ("signal_type", "signalType", "type"):
        raw = args.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    # Batch payloads: signals=[{signal_type: ...}, ...]
    for key in ("signals", "signal_specs", "items", "orders"):
        items = args.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for sk in ("signal_type", "signalType", "type"):
                        raw = item.get(sk)
                        if raw is not None and str(raw).strip():
                            st = str(raw).strip()
                            from duckclaw.signal_execution_bridge import is_protective_signal_type

                            if is_protective_signal_type(st):
                                return st
    return None


def _peek_signal_type_from_db(db: Any, signal_id: str) -> str | None:
    """Best-effort read of finance_worker.trade_signals.signal_type (RO)."""
    sid = (signal_id or "").strip()
    if not sid or db is None:
        return None
    try:
        rows = db.execute(
            """
            SELECT signal_type
            FROM finance_worker.trade_signals
            WHERE lower(cast(signal_id AS VARCHAR)) = lower(?)
            LIMIT 1
            """,
            [sid],
        ).fetchall()
        if rows:
            return str(rows[0][0] or "").strip() or None
    except Exception:
        _log.debug("protective route: trade_signals peek failed", exc_info=True)
    try:
        rows = db.execute(
            """
            SELECT signal_type
            FROM quant_core.trade_signals
            WHERE lower(cast(signal_id AS VARCHAR)) = lower(?)
            LIMIT 1
            """,
            [sid],
        ).fetchall()
        if rows:
            return str(rows[0][0] or "").strip() or None
    except Exception:
        _log.debug("protective route: quant_core.trade_signals peek failed", exc_info=True)
    return None


def blocked_protective_broker_route(
    tool_name: str,
    args: Any = None,
    *,
    db: Any = None,
) -> Optional[str]:
    """Return a JSON error string if this tool call must not market-enter.

    Returns None when the call is allowed (ENTRY/EXIT or non-broker tool).
    """
    name = (tool_name or "").strip()
    if name not in _MARKET_ENTRY_BROKER_TOOLS:
        return None

    from duckclaw.signal_execution_bridge import (
        is_protective_signal_type,
        refuse_protective_as_market_entry,
        text_indicates_protective_order,
    )

    st = _signal_type_from_args(args)
    if st is None and name == "execute_approved_signal" and isinstance(args, dict):
        sid = str(args.get("signal_id") or "").strip()
        if sid:
            st = _peek_signal_type_from_db(db, sid)

    refused = refuse_protective_as_market_entry(st) if st else None
    if refused is None and text_indicates_protective_order(_args_blob(args)):
        # Args/rationale mention BRACKET/OCA without an explicit ENTRY — block.
        if not st or is_protective_signal_type(st):
            refused = refuse_protective_as_market_entry(st or "BRACKET")

    if refused is None:
        return None

    payload = {
        **refused,
        "tool": name,
        "hint": (
            "Use execute_signal_with_bracket(..., signal_type='BRACKET') or "
            "scripts/place_protective_gtc_brackets.py / TWS OCA. "
            "Do not call execute_approved_signal for protective brackets."
        ),
    }
    _log.warning(
        "BLOCKED_PROTECTIVE_ORDER_ROUTE tool=%s signal_type=%s",
        name,
        refused.get("signal_type"),
    )
    return json.dumps(payload, ensure_ascii=False)
