"""
Propuesta y ejecución de señales (quant_core.trade_signals) con HITL vía quant_hitl.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Optional

from duckclaw.forge.skills.quant_hitl import consume_execute_order_grant
from duckclaw.forge.skills.quant_tool_context import get_quant_tool_chat_id
from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)


def _risk_level(spec: Any) -> str:
    rl = (getattr(spec, "risk_level", None) or "conservative").strip().lower()
    return rl if rl in ("aggressive", "conservative") else "conservative"


@log_tool_execution_sync(name="propose_trade")
def _propose_trade_impl(
    db: Any,
    spec: Any,
    *,
    ticker: str,
    action: str,
    qty: float,
    limit_price: float = 0.0,
    stop_loss: float = 0.0,
    confidence_score: float = 0.5,
    strategy_name: str = "manual",
) -> str:
    tkr = (ticker or "").strip().upper()
    act = (action or "").strip().upper()
    if not tkr or act not in ("BUY", "SELL", "HOLD"):
        return json.dumps({"error": "ticker y action (BUY|SELL|HOLD) son obligatorios."}, ensure_ascii=False)
    rl = _risk_level(spec)
    if rl != "aggressive" and act in ("SHORT", "MARGIN"):
        return json.dumps({"error": "Short/margin requiere risk_level: aggressive en manifest."}, ensure_ascii=False)
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return json.dumps({"error": "qty inválido."}, ensure_ascii=False)
    if rl == "conservative" and q < 0:
        return json.dumps({"error": "Cantidad negativa no permitida en modo conservative."}, ensure_ascii=False)

    sid = str(uuid.uuid4())
    strat = (strategy_name or "manual")[:128]
    try:
        db.execute(
            """
            INSERT INTO quant_core.trade_signals
            (signal_id, ticker, strategy_name, action, confidence_score, target_price, stop_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                tkr,
                strat,
                act,
                float(confidence_score),
                float(limit_price),
                float(stop_loss),
            ),
        )
    except Exception as e:
        _log.warning("[quant_trade] insert signal failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    return json.dumps(
        {
            "status": "proposed",
            "signal_id": sid,
            "ticker": tkr,
            "action": act,
            "hint": "El usuario debe confirmar con /execute_signal " + sid + " antes de execute_order.",
        },
        ensure_ascii=False,
    )


@log_tool_execution_sync(name="execute_order")
def _execute_order_impl(db: Any, spec: Any, signal_id: str) -> str:
    sid = (signal_id or "").strip().lower()
    if not sid or len(sid) < 32:
        return json.dumps({"error": "signal_id UUID inválido."}, ensure_ascii=False)
    chat_id = get_quant_tool_chat_id() or "default"
    if not consume_execute_order_grant(chat_id, sid):
        return json.dumps(
            {
                "error": (
                    "Orden bloqueada: confirma primero con /execute_signal " + sid + " en Telegram "
                    "(human-in-the-loop)."
                )
            },
            ensure_ascii=False,
        )

    mode = (os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    if mode != "paper":
        return json.dumps(
            {"error": "Solo cuenta paper está permitida (IBKR_ACCOUNT_MODE=paper)."},
            ensure_ascii=False,
        )

    url = (os.environ.get("IBKR_EXECUTE_ORDER_URL") or "").strip()
    if not url:
        return json.dumps(
            {
                "status": "simulated",
                "signal_id": sid,
                "message": (
                    "HITL OK; IBKR_EXECUTE_ORDER_URL no configurada — orden no enviada al broker. "
                    "Configura el endpoint paper cuando esté listo."
                ),
            },
            ensure_ascii=False,
        )

    token = (os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_ORDER_API_KEY") or "").strip()
    payload = json.dumps({"signal_id": sid, "paper": True}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"Broker HTTP {e.code}"}, ensure_ascii=False)
    except urllib.error.URLError as e:
        return json.dumps({"error": str(e.reason)}, ensure_ascii=False)
    return json.dumps({"status": "sent", "signal_id": sid, "broker_response": body[:2000]}, ensure_ascii=False)


def register_quant_trade_skills(db: Any, spec: Any, tools: list[Any]) -> None:
    from langchain_core.tools import StructuredTool

    def _propose(
        ticker: str,
        action: str,
        qty: float,
        limit_price: float = 0.0,
        stop_loss: float = 0.0,
        confidence_score: float = 0.5,
        strategy_name: str = "manual",
    ) -> str:
        return _propose_trade_impl(
            db,
            spec,
            ticker=ticker,
            action=action,
            qty=qty,
            limit_price=limit_price,
            stop_loss=stop_loss,
            confidence_score=confidence_score,
            strategy_name=strategy_name,
        )

    def _execute(signal_id: str) -> str:
        return _execute_order_impl(db, spec, signal_id)

    tools.append(
        StructuredTool.from_function(
            _propose,
            name="propose_trade",
            description=(
                "Registra una señal en quant_core.trade_signals (no ejecuta en bolsa). "
                "Parámetros: ticker, action BUY|SELL|HOLD, qty, limit_price, stop_loss, confidence_score, strategy_name. "
                "Tras la propuesta el usuario debe usar /execute_signal <uuid> y luego puedes llamar execute_order."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute,
            name="execute_order",
            description=(
                "Ejecuta orden en broker SOLO si el usuario confirmó con /execute_signal y el mismo signal_id. "
                "Requiere IBKR_ACCOUNT_MODE=paper. Parámetro: signal_id (UUID)."
            ),
        )
    )
