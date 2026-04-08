"""Skills del worker Quant Trader (StateDelta + RiskGuard + HITL)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any

from duckclaw.forge.skills.quant_market_bridge import _fetch_market_data_impl
from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync
from duckclaw.forge.skills.quant_tool_context import (
    get_quant_tool_db_path,
    get_quant_tool_tenant_id,
    get_quant_tool_user_id,
    has_quant_market_evidence_for_ticker,
)
from duckclaw.graphs.sandbox import run_in_sandbox
from duckclaw.utils.logger import log_tool_execution_sync


def _max_weight_pct_limit() -> float:
    raw = (os.environ.get("DUCKCLAW_QUANT_MAX_WEIGHT_PCT") or "10").strip()
    try:
        return max(0.1, min(100.0, float(raw)))
    except ValueError:
        return 10.0


def _liquid_capital(db: Any) -> float:
    try:
        raw = db.query(
            "SELECT COALESCE(SUM(balance),0) AS liquid FROM finance_worker.cuentas WHERE balance > 0"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return float(rows[0].get("liquid") or 0.0)
    except Exception:
        return 0.0
    return 0.0


def _state_delta_base() -> dict[str, str]:
    return {
        "tenant_id": get_quant_tool_tenant_id() or "default",
        "user_id": get_quant_tool_user_id() or "default",
        "target_db_path": get_quant_tool_db_path() or "",
    }


@log_tool_execution_sync(name="execute_sandbox_script")
def _execute_sandbox_script_impl(
    db: Any, llm: Any, *, code: str, dependencies: list[str] | None = None
) -> str:
    _ = dependencies
    result = run_in_sandbox(
        db=db,
        llm=llm,
        code=code,
        language="python",
        original_request="quant backtest script",
        max_retries=1,
        worker_id="quant_trader",
    )
    payload = {
        "exit_code": int(result.exit_code),
        "stdout": (result.stdout or "")[:8000],
        "stderr": (result.stderr or "")[:4000],
    }
    if int(result.exit_code) != 0:
        payload["error"] = "SANDBOX_EXECUTION_FAILED"
    return json.dumps(payload, ensure_ascii=False)


@log_tool_execution_sync(name="propose_trade_signal")
def _propose_trade_signal_impl(
    db: Any,
    *,
    mandate_id: str,
    ticker: str,
    weight: float,
    rationale: str = "",
    signal_type: str = "ENTRY",
    sandbox_backtest_cid: str = "",
) -> str:
    tkr = (ticker or "").strip().upper()
    mid = (mandate_id or "").strip() or str(uuid.uuid4())
    if not tkr:
        return json.dumps({"error": "ticker requerido"}, ensure_ascii=False)
    if not has_quant_market_evidence_for_ticker(tkr):
        return json.dumps(
            {
                "error": "EVIDENCE_UNIQUE_RULE",
                "message": f"No existe fetch_market_data exitoso para {tkr} en este turno.",
            },
            ensure_ascii=False,
        )
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return json.dumps({"error": "weight inválido"}, ensure_ascii=False)
    cap = _liquid_capital(db)
    limit = _max_weight_pct_limit()
    guarded = max(0.0, min(w, limit))
    rr = (rationale or "").strip()
    if guarded < w:
        rr = (rr + " " if rr else "") + f"RiskGuard ajustó peso de {w:.2f}% a {guarded:.2f}% (límite tenant)."

    base = _state_delta_base()
    if not base["target_db_path"]:
        try:
            base["target_db_path"] = str(getattr(db, "_path", "") or "")
        except Exception:
            base["target_db_path"] = ""
    if not base["target_db_path"]:
        return json.dumps({"error": "target_db_path no resuelto para StateDelta"}, ensure_ascii=False)

    signal_id = str(uuid.uuid4())
    ok_m = push_quant_state_delta_sync(
        {
            **base,
            "delta_type": "MANDATE_UPSERT",
            "mutation": {
                "mandate_id": mid,
                "source_worker": "finanz",
                "asset_class": "EQUITY",
                "direction": "LONG" if str(signal_type).upper() == "ENTRY" else "NEUTRAL",
                "max_weight_pct": float(limit),
                "status": "ANALYZING",
            },
        }
    )
    ok_s = push_quant_state_delta_sync(
        {
            **base,
            "delta_type": "TRADE_SIGNAL_PROPOSED",
            "mutation": {
                "signal_id": signal_id,
                "mandate_id": mid,
                "ticker": tkr,
                "signal_type": "ENTRY" if str(signal_type).upper() != "EXIT" else "EXIT",
                "proposed_weight": float(guarded),
                "sandbox_backtest_cid": (sandbox_backtest_cid or "").strip(),
                "human_approved": False,
                "status": "AWAITING_HITL",
                "rationale": rr,
            },
        }
    )
    if not (ok_m and ok_s):
        return json.dumps({"error": "No se pudo encolar StateDelta en Redis"}, ensure_ascii=False)
    return json.dumps(
        {
            "status": "AWAITING_HITL",
            "signal_id": signal_id,
            "mandate_id": mid,
            "ticker": tkr,
            "proposed_weight": guarded,
            "liquid_capital": cap,
            "hint": f"Senal {signal_id} lista. Requiere /execute_signal {signal_id}",
        },
        ensure_ascii=False,
    )


@log_tool_execution_sync(name="execute_approved_signal")
def _execute_approved_signal_impl(db: Any, *, signal_id: str) -> str:
    sid = (signal_id or "").strip().lower()
    if not sid:
        return json.dumps({"error": "signal_id requerido"}, ensure_ascii=False)
    try:
        raw = db.query(
            "SELECT human_approved, status FROM finance_worker.trade_signals WHERE signal_id='"
            + sid
            + "' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return json.dumps({"error": f"DB_READ_FAILED: {exc}"}, ensure_ascii=False)
    if not rows:
        return json.dumps({"error": "signal no existe"}, ensure_ascii=False)
    row = rows[0] if isinstance(rows[0], dict) else {}
    if not bool(row.get("human_approved")):
        return json.dumps({"error": "human_approved != TRUE"}, ensure_ascii=False)
    if str(row.get("status") or "").upper() == "DISCARDED":
        return json.dumps({"error": "signal stale/discarded"}, ensure_ascii=False)
    mode = (os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    if mode != "paper":
        return json.dumps({"error": "Solo paper trading permitido"}, ensure_ascii=False)

    url = (os.environ.get("IBKR_EXECUTE_ORDER_URL") or "").strip()
    if not url:
        push_quant_state_delta_sync(
            {
                **_state_delta_base(),
                "target_db_path": get_quant_tool_db_path() or str(getattr(db, "_path", "") or ""),
                "delta_type": "TRADE_SIGNAL_EXECUTED",
                "mutation": {"signal_id": sid},
            }
        )
        return json.dumps(
            {
                "status": "simulated",
                "signal_id": sid,
                "message": "HITL OK; endpoint IBKR no configurado, ejecucion simulada.",
            },
            ensure_ascii=False,
        )

    payload = json.dumps({"signal_id": sid, "paper": True}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    token = (os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_ORDER_API_KEY") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return json.dumps({"error": f"Broker HTTP {exc.code}"}, ensure_ascii=False)
    except urllib.error.URLError as exc:
        return json.dumps({"error": str(exc.reason)}, ensure_ascii=False)

    push_quant_state_delta_sync(
        {
            **_state_delta_base(),
            "target_db_path": get_quant_tool_db_path() or str(getattr(db, "_path", "") or ""),
            "delta_type": "TRADE_SIGNAL_EXECUTED",
            "mutation": {"signal_id": sid},
        }
    )
    return json.dumps({"status": "sent", "signal_id": sid, "broker_response": body[:2000]}, ensure_ascii=False)


def register_quant_trader_skills(db: Any, llm: Any, tools: list[Any]) -> None:
    from langchain_core.tools import StructuredTool

    def _fetch_market_data(ticker: str, timeframe: str = "1d", lookback_days: int = 365) -> str:
        return _fetch_market_data_impl(
            db,
            ticker=ticker,
            timeframe=timeframe,
            lookback_days=int(lookback_days),
        )

    def _execute_sandbox_script(code: str, dependencies: list[str] | None = None) -> str:
        return _execute_sandbox_script_impl(db, llm, code=code, dependencies=dependencies)

    def _propose_trade_signal(
        mandate_id: str,
        ticker: str,
        weight: float,
        rationale: str = "",
        signal_type: str = "ENTRY",
        sandbox_backtest_cid: str = "",
    ) -> str:
        return _propose_trade_signal_impl(
            db,
            mandate_id=mandate_id,
            ticker=ticker,
            weight=weight,
            rationale=rationale,
            signal_type=signal_type,
            sandbox_backtest_cid=sandbox_backtest_cid,
        )

    def _execute_approved_signal(signal_id: str) -> str:
        return _execute_approved_signal_impl(db, signal_id=signal_id)

    tools.append(
        StructuredTool.from_function(
            _fetch_market_data,
            name="fetch_market_data",
            description="Obtiene OHLCV y persiste en quant_core.ohlcv_data para evidencia del turno.",
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute_sandbox_script,
            name="execute_sandbox_script",
            description="Ejecuta script de backtesting en sandbox aislado (timeout estricto).",
        )
    )
    tools.append(
        StructuredTool.from_function(
            _propose_trade_signal,
            name="propose_trade_signal",
            description=(
                "Propone una senal en finance_worker.trade_signals via StateDelta; aplica EvidenceUnique y RiskGuard."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute_approved_signal,
            name="execute_approved_signal",
            description="Ejecuta una senal aprobada por HITL (human_approved=TRUE) en paper trading.",
        )
    )
