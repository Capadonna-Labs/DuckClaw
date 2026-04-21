"""Skills del worker Quant Trader (StateDelta + RiskGuard + HITL)."""

from __future__ import annotations

import json
import os
import statistics
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_total_equity_numeric
from duckclaw.forge.skills.quant_market_bridge import (
    _fetch_ib_gateway_ohlcv_impl,
    _fetch_market_data_impl,
)
from duckclaw.forge.skills.quant_cfd_bridge import _record_fluid_state_impl
from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync
from duckclaw.forge.skills.quant_hitl import consume_execute_order_grant
from duckclaw.forge.skills.quant_tool_context import (
    get_quant_tool_chat_id,
    get_quant_tool_db_path,
    get_quant_tool_tenant_id,
    get_quant_tool_user_id,
    has_quant_market_evidence_for_ticker,
    note_quant_market_evidence_ticker,
)
from duckclaw.graphs.sandbox import run_in_sandbox
from duckclaw.utils.logger import log_tool_execution_sync


def _derive_ibkr_execute_order_url_from_portfolio() -> str:
    """
    Si ``IBKR_EXECUTE_ORDER_URL`` no está definido pero sí ``IBKR_PORTFOLIO_API_URL``
    (mismo host :8002), usa ``/api/broker/execute`` para que paper/live envíen orden al hook VPS.
    """
    p = (os.environ.get("IBKR_PORTFOLIO_API_URL") or "").strip()
    if not p:
        return ""
    if "/api/broker/execute" in p:
        return p.split("/api/broker/execute")[0].rstrip("/") + "/api/broker/execute"
    if "/api/portfolio/" in p:
        base = p.split("/api/portfolio/")[0].rstrip("/")
        return f"{base}/api/broker/execute"
    return ""


def _ibkr_execute_order_timeout_sec() -> float:
    """
    Timeout del POST al hook de ejecución (``/api/broker/execute`` o ``IBKR_EXECUTE_ORDER_URL``).

    Prioridad: ``IBKR_EXECUTE_ORDER_TIMEOUT_SEC`` → ``IBKR_HTTP_TIMEOUT_SEC`` /
    ``IBKR_GATEWAY_HTTP_TIMEOUT_SEC`` (mismo criterio que ``quant_market_bridge``) → 120s.
    Rango: 30–600s (ejecución IBKR puede superar 45s en redes lentas o colas).
    """
    raw = (
        os.environ.get("IBKR_EXECUTE_ORDER_TIMEOUT_SEC")
        or os.environ.get("IBKR_HTTP_TIMEOUT_SEC")
        or os.environ.get("IBKR_GATEWAY_HTTP_TIMEOUT_SEC")
        or "120"
    ).strip()
    try:
        t = float(raw)
    except ValueError:
        t = 120.0
    return float(max(30, min(t, 600)))


def _is_broker_post_timeout(exc: BaseException) -> bool:
    """True si ``urlopen`` falló por tiempo de espera (no confundir con 'connection refused')."""
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    s = (str(reason) + " " + str(exc)).lower()
    return "timed out" in s


def _broker_message_from_http_error(exc: urllib.error.HTTPError) -> str:
    """Extrae ``message`` del JSON de error del broker (p. ej. 501 Problem Details)."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            m = d.get("message")
            if isinstance(m, str) and m.strip():
                return m.strip()[:2000]
    except json.JSONDecodeError:
        pass
    return (raw or "")[:500]


def _max_weight_pct_limit() -> float:
    raw = (os.environ.get("DUCKCLAW_QUANT_MAX_WEIGHT_PCT") or "10").strip()
    try:
        return max(0.1, min(100.0, float(raw)))
    except ValueError:
        return 10.0


def _normalize_proposed_weight_pct(raw: float) -> float:
    """
    Alinea con el hook ``broker_execute_signal.py``: ``notional = equity * (peso/100)``.

    El LLM a menudo pasa **fracción** (0.03 = 3%); el hook espera **porcentaje** (3 = 3%).
    Regla: ``0 < w < 1`` se interpreta como fracción del 100% y se multiplica por 100.
    ``w >= 1`` se deja como porcentaje (1 = 1%, 15 = 15%).
    """
    try:
        w = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if w <= 0:
        return w
    if 0 < w < 1.0:
        return w * 100.0
    return w


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


def _coerce_mandate_id_to_uuid(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return str(uuid.uuid4())
    try:
        uuid.UUID(s)
        return s
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "duckclaw:mandate:" + s))


def quant_trading_session_prompt_block(db: Any) -> str:
    """Contexto de sesión ACTIVE + riesgo para inyectar en system prompt (modo reactor)."""
    try:
        raw = db.query(
            "SELECT mode, tickers, status, session_uid FROM quant_core.trading_sessions "
            "WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return ""
    if not rows or not isinstance(rows[0], dict):
        return ""
    row = rows[0]
    if str(row.get("status") or "").strip().upper() != "ACTIVE":
        return ""
    max_dd_s = ""
    try:
        raw2 = db.query(
            "SELECT max_drawdown_pct FROM quant_core.trading_risk_constraints WHERE id = 'active' LIMIT 1"
        )
        r2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or [])
        if r2 and isinstance(r2[0], dict) and r2[0].get("max_drawdown_pct") is not None:
            max_dd_s = f"\n- Límite DD (bóveda): {float(r2[0]['max_drawdown_pct']) * 100:.2f}%"
    except Exception:
        pass
    tickers = (row.get("tickers") or "").strip()
    uid = (row.get("session_uid") or "").strip()
    mode = (row.get("mode") or "").strip()
    return (
        "## Sesión de trading (reactor)\n"
        f"- Estado: **ACTIVE** · modo `{mode}` · session_uid `{uid}`\n"
        f"- Tickers: `{tickers or '(cualquiera)'}`{max_dd_s}\n"
        "Mientras la sesión esté ACTIVE, evalúa mercado con herramientas, respeta el límite de DD si existe, "
        "y si hay setup válido propón señal con `propose_trade_signal` (tras evidencia OHLCV del ticker)."
    )


def _quant_drawdown_risk_gate(db: Any) -> Optional[Tuple[str, str]]:
    """
    Sesión ACTIVE + max_drawdown_pct en bóveda: fail-closed sin equity IBKR; bloquea si DD > techo.
    DD de sesión = (peak_equity - equity_now) / peak_equity; peak se actualiza en memoria y vía UPDATE si el handle lo permite.
    """
    try:
        raw = db.query(
            "SELECT status, peak_equity FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    st = str(rows[0].get("status") or "").strip().upper()
    if st != "ACTIVE":
        return None
    try:
        raw2 = db.query(
            "SELECT max_drawdown_pct FROM quant_core.trading_risk_constraints WHERE id = 'active' LIMIT 1"
        )
        rows2 = json.loads(raw2) if isinstance(raw2, str) else (raw2 or [])
    except Exception:
        rows2 = []
    max_dd: Optional[float] = None
    if rows2 and isinstance(rows2[0], dict) and rows2[0].get("max_drawdown_pct") is not None:
        try:
            max_dd = float(rows2[0]["max_drawdown_pct"])
        except (TypeError, ValueError):
            max_dd = None
    if max_dd is None or max_dd <= 0:
        return None
    eq, err = fetch_ibkr_total_equity_numeric()
    if eq is None:
        return (
            "RISK_EQUITY_UNAVAILABLE",
            f"Límite DD activo pero no se pudo leer equity IBKR ({err}). No se registra la señal.",
        )
    try:
        peak_db = rows[0].get("peak_equity")
        peak = float(peak_db) if peak_db is not None else float(eq)
    except (TypeError, ValueError):
        peak = float(eq)
    peak = max(peak, float(eq))
    try:
        exe = getattr(db, "execute", None)
        if callable(exe):
            exe(
                "UPDATE quant_core.trading_sessions SET peak_equity = ? WHERE id = 'active'",
                [peak],
            )
    except Exception:
        pass
    if peak <= 0:
        return None
    dd = (peak - float(eq)) / peak
    if dd > max_dd:
        return (
            "RISK_GOAL_BREACH",
            f"Drawdown de sesión {dd * 100:.2f}% supera el máximo {max_dd * 100:.2f}%. No se registra la señal.",
        )
    return None


def _trading_session_mode(db: Any) -> str:
    """Lee quant_core.trading_sessions (singleton id=active). Sin fila → paper."""
    try:
        raw = db.query(
            "SELECT mode FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            m = str(rows[0].get("mode") or "paper").strip().lower()
            if m in ("paper", "live"):
                return m
    except Exception:
        pass
    return "paper"


def _active_session_snapshot(db: Any) -> dict[str, Any]:
    try:
        raw = db.query(
            "SELECT mode, tickers, status, session_uid, session_goal FROM quant_core.trading_sessions "
            "WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return rows[0]
    except Exception:
        pass
    return {}


def _phase_from_temperature(temp: float) -> str:
    if temp < 0.002:
        return "SOLID"
    if temp < 0.008:
        return "LIQUID"
    if temp < 0.02:
        return "GAS"
    return "PLASMA"


def _phase_rank(phase: str) -> int:
    p = str(phase or "").strip().upper()
    return {"SOLID": 1, "LIQUID": 2, "GAS": 3, "PLASMA": 4}.get(p, 0)


@log_tool_execution_sync(name="evaluate_cfd_state")
def _evaluate_cfd_state_impl(
    db: Any,
    *,
    session_uid: str,
    tickers: list[str],
    signal_threshold: str = "GAS",
) -> str:
    sess = _active_session_snapshot(db)
    if not sess or str(sess.get("status") or "").strip().upper() != "ACTIVE":
        return json.dumps(
            {"status": "ok", "session_active": False, "message": "No hay sesión activa. Tick cancelado."},
            ensure_ascii=False,
        )
    active_uid = str(sess.get("session_uid") or "").strip()
    if session_uid and active_uid and session_uid != active_uid:
        return json.dumps(
            {
                "status": "ok",
                "session_active": False,
                "message": f"session_uid desfasado ({session_uid} != {active_uid}). Tick cancelado.",
            },
            ensure_ascii=False,
        )
    threshold = str(signal_threshold or "GAS").strip().upper() or "GAS"
    req_tickers = [str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip()]
    if not req_tickers:
        req_tickers = [x.strip().upper() for x in str(sess.get("tickers") or "").split(",") if x.strip()]
    if not req_tickers:
        return json.dumps(
            {"status": "ok", "session_active": True, "all_data_failed": True, "results": []},
            ensure_ascii=False,
        )
    results: list[dict[str, Any]] = []
    any_ok = False
    for tkr in req_tickers:
        raw = _fetch_market_data_impl(db, ticker=tkr, timeframe="15m", lookback_days=5)
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": "fetch_market_data_invalid_json"}
        if not isinstance(payload, dict) or payload.get("error"):
            results.append(
                {
                    "ticker": tkr,
                    "ok": False,
                    "error": str(payload.get("error") or "fetch_market_data_failed"),
                }
            )
            continue
        try:
            esc_tkr = tkr.replace("'", "''")
            rows_raw = db.query(
                "SELECT close, volume, timestamp FROM quant_core.ohlcv_data "
                f"WHERE ticker = '{esc_tkr}' "
                "ORDER BY timestamp DESC LIMIT 25"
            )
            rows = json.loads(rows_raw) if isinstance(rows_raw, str) else (rows_raw or [])
        except Exception:
            rows = []
        closes: list[float] = []
        masses: list[float] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                c = float(row.get("close") or 0.0)
                v = float(row.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            closes.append(c)
            masses.append(c * max(0.0, v))
        if len(closes) < 3:
            results.append({"ticker": tkr, "ok": False, "error": "insufficient_ohlcv"})
            continue
        rets: list[float] = []
        for i in range(1, len(closes)):
            prev = closes[i]
            now = closes[i - 1]
            if prev > 0:
                rets.append((now - prev) / prev)
        temp = float(statistics.pstdev(rets)) if len(rets) > 1 else 0.0
        mass = float(masses[0]) if masses else 0.0
        phase = _phase_from_temperature(temp)
        _ = _record_fluid_state_impl(
            db,
            ticker=tkr,
            phase=phase,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            mass=mass,
            temperature=temp,
        )
        has_pending = False
        try:
            esc_tkr2 = tkr.replace("'", "''")
            pending_raw = db.query(
                "SELECT signal_id FROM finance_worker.trade_signals "
                f"WHERE ticker = '{esc_tkr2}' "
                "AND status IN ('PENDING_HITL','AWAITING_HITL','PENDING') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            pending_rows = json.loads(pending_raw) if isinstance(pending_raw, str) else (pending_raw or [])
            has_pending = bool(pending_rows)
        except Exception:
            has_pending = False
        any_ok = True
        results.append(
            {
                "ticker": tkr,
                "ok": True,
                "temperature": temp,
                "mass": mass,
                "phase": phase,
                "phase_rank": _phase_rank(phase),
                "threshold_rank": _phase_rank(threshold),
                "has_pending_hitl": has_pending,
            }
        )
    if not any_ok:
        return json.dumps(
            {
                "status": "ok",
                "session_active": True,
                "all_data_failed": True,
                "signal_threshold": threshold,
                "results": results,
            },
            ensure_ascii=False,
        )
    aligned = all(
        (not r.get("ok"))
        or (int(r.get("phase_rank") or 0) < int(r.get("threshold_rank") or 0))
        or bool(r.get("has_pending_hitl"))
        for r in results
    )
    return json.dumps(
        {
            "status": "ok",
            "session_active": True,
            "session_uid": active_uid or session_uid,
            "signal_threshold": threshold,
            "results": results,
            "outcome": "ALIGNED" if aligned else "MISALIGNED",
            "all_data_failed": False,
        },
        ensure_ascii=False,
    )


def _push_signal_failed(db: Any, sid: str) -> None:
    push_quant_state_delta_sync(
        {
            **_state_delta_base(),
            "target_db_path": get_quant_tool_db_path() or str(getattr(db, "_path", "") or ""),
            "delta_type": "TRADE_SIGNAL_FAILED",
            "mutation": {"signal_id": sid},
        }
    )


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
    mid_in = (mandate_id or "").strip()
    mid = str(uuid.uuid4()) if not mid_in else _coerce_mandate_id_to_uuid(mid_in)
    if not tkr:
        return json.dumps({"error": "ticker requerido"}, ensure_ascii=False)
    if not has_quant_market_evidence_for_ticker(tkr):
        return json.dumps(
            {
                "error": "EVIDENCE_UNIQUE_RULE",
                "message": f"No existe fetch_market_data o fetch_ib_gateway_ohlcv exitoso para {tkr} en este turno.",
            },
            ensure_ascii=False,
        )
    risk_block = _quant_drawdown_risk_gate(db)
    if risk_block:
        code, msg = risk_block
        return json.dumps({"error": code, "message": msg}, ensure_ascii=False)
    try:
        w = float(weight)
    except (TypeError, ValueError):
        return json.dumps({"error": "weight inválido"}, ensure_ascii=False)
    w = _normalize_proposed_weight_pct(w)
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
    sess = _active_session_snapshot(db)
    session_uid = str(sess.get("session_uid") or "").strip()
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
                "status": "PENDING_HITL",
                "rationale": rr,
                "session_uid": session_uid,
            },
        }
    )
    if not (ok_m and ok_s):
        return json.dumps({"error": "No se pudo encolar StateDelta en Redis"}, ensure_ascii=False)
    return json.dumps(
        {
            "status": "PENDING_HITL",
            "session_uid": session_uid,
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
            "SELECT human_approved, status, ticker, signal_type, proposed_weight, mandate_id "
            "FROM finance_worker.trade_signals WHERE signal_id='"
            + sid
            + "' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:
        return json.dumps({"error": f"DB_READ_FAILED: {exc}"}, ensure_ascii=False)
    if not rows:
        return json.dumps({"error": "signal no existe"}, ensure_ascii=False)
    row = rows[0] if isinstance(rows[0], dict) else {}
    hitl_ok = bool(row.get("human_approved"))
    if not hitl_ok:
        cid = get_quant_tool_chat_id() or "default"
        if consume_execute_order_grant(cid, sid):
            hitl_ok = True
    if not hitl_ok:
        return json.dumps(
            {
                "error": "human_approved != TRUE",
                "message": (
                    "Confirma con /execute_signal " + sid + " en Telegram y vuelve a llamar execute_approved_signal."
                ),
            },
            ensure_ascii=False,
        )
    if str(row.get("status") or "").upper() in ("DISCARDED", "CANCELLED"):
        return json.dumps({"error": "signal stale/discarded"}, ensure_ascii=False)
    session_mode = _trading_session_mode(db)
    env_mode = (os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    if session_mode == "live" and env_mode != "live":
        return json.dumps(
            {
                "error": "TRADING_SESSION_LIVE_REQUIRES_IBKR_ACCOUNT_MODE_LIVE",
                "message": "La sesión en quant_core.trading_sessions es live; define IBKR_ACCOUNT_MODE=live.",
            },
            ensure_ascii=False,
        )
    # Paper/live de ejecución lo marca la sesión (paper_flag); IBKR_ACCOUNT_MODE refleja
    # el snapshot de portfolio en el host, no debe bloquear una sesión paper con env live.

    paper_flag = session_mode != "live"
    tgt = get_quant_tool_db_path() or str(getattr(db, "_path", "") or "")

    exec_timeout_sec = _ibkr_execute_order_timeout_sec()

    url = (os.environ.get("IBKR_EXECUTE_ORDER_URL") or "").strip()
    _explicit_exec = bool(url)
    if not url:
        url = _derive_ibkr_execute_order_url_from_portfolio()
    # #region agent log
    try:
        import time as _time_dbg_ex

        _payload_ex = {
            "sessionId": "c964f7",
            "hypothesisId": "H_execute_broker_path",
            "location": "quant_trader_bridge.py:_execute_approved_signal_impl",
            "message": "execute_signal_url_resolution",
            "data": {
                "explicit_IBKR_EXECUTE_ORDER_URL": _explicit_exec,
                "derived_url_nonempty": bool((url or "").strip()) and not _explicit_exec,
                "resolved_url_nonempty": bool((url or "").strip()),
                "paper_flag": paper_flag,
                "will_simulate": not bool((url or "").strip()),
                "timeout_sec": exec_timeout_sec,
            },
            "timestamp": int(_time_dbg_ex.time() * 1000),
        }
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as _df_ex:
            _df_ex.write(json.dumps(_payload_ex) + "\n")
    except Exception:
        pass
    # #endregion
    if not url:
        push_quant_state_delta_sync(
            {
                **_state_delta_base(),
                "target_db_path": tgt,
                "delta_type": "TRADE_SIGNAL_EXECUTED",
                "mutation": {"signal_id": sid},
            }
        )
        return json.dumps(
            {
                "status": "simulated",
                "signal_id": sid,
                "paper": paper_flag,
                "message": "HITL OK; endpoint IBKR no configurado, ejecucion simulada.",
            },
            ensure_ascii=False,
        )

    sig_row = row if isinstance(row, dict) else {}
    post: dict[str, Any] = {"signal_id": sid, "paper": paper_flag}
    tkr = str(sig_row.get("ticker") or "").strip().upper()
    if tkr:
        post["ticker"] = tkr
    st = str(sig_row.get("signal_type") or "").strip().upper()
    if st in ("ENTRY", "EXIT"):
        post["signal_type"] = st
    try:
        pw = float(sig_row.get("proposed_weight"))
        if pw > 0:
            post["proposed_weight"] = _normalize_proposed_weight_pct(pw)
    except (TypeError, ValueError):
        pass
    mid = str(sig_row.get("mandate_id") or "").strip()
    if mid:
        post["mandate_id"] = mid
    payload = json.dumps(post, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header(
        "X-Duckclaw-IBKR-Account-Mode",
        "paper" if paper_flag else "live",
    )
    token = (os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_ORDER_API_KEY") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    broker_parsed: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(req, timeout=exec_timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        _push_signal_failed(db, sid)
        broker_msg = _broker_message_from_http_error(exc)
        err_obj: dict[str, Any] = {"error": f"Broker HTTP {exc.code}"}
        if broker_msg:
            err_obj["broker_message"] = broker_msg
        return json.dumps(err_obj, ensure_ascii=False)
    except urllib.error.URLError as exc:
        _push_signal_failed(db, sid)
        if _is_broker_post_timeout(exc):
            return json.dumps(
                {
                    "error": "BROKER_TIMEOUT",
                    "message": (
                        "El hook de ejecución no respondió a tiempo. "
                        "Aumenta IBKR_EXECUTE_ORDER_TIMEOUT_SEC (actual "
                        f"{exec_timeout_sec:.0f}s) o revisa el servicio en el host del broker."
                    ),
                    "timeout_sec": exec_timeout_sec,
                },
                ensure_ascii=False,
            )
        return json.dumps({"error": str(exc.reason)}, ensure_ascii=False)

    try:
        if body.strip().startswith("{"):
            _bp = json.loads(body)
            if isinstance(_bp, dict):
                broker_parsed = _bp
    except json.JSONDecodeError:
        broker_parsed = {}
    # #region agent log
    try:
        import time as _time_dbg_br

        _payload_br = {
            "sessionId": "c964f7",
            "hypothesisId": "H_broker_response_parsed",
            "location": "quant_trader_bridge.py:_execute_approved_signal_impl",
            "message": "broker_http_ok_body",
            "data": {
                "signal_id": sid,
                "broker_status": broker_parsed.get("status"),
                "ib_order_id": broker_parsed.get("ib_order_id"),
                "qty": broker_parsed.get("qty"),
                "ticker": broker_parsed.get("ticker"),
                "posted_weight_after_normalize": post.get("proposed_weight"),
            },
            "timestamp": int(_time_dbg_br.time() * 1000),
        }
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as _df_br:
            _df_br.write(json.dumps(_payload_br) + "\n")
    except Exception:
        pass
    # #endregion

    push_quant_state_delta_sync(
        {
            **_state_delta_base(),
            "target_db_path": tgt,
            "delta_type": "TRADE_SIGNAL_EXECUTED",
            "mutation": {"signal_id": sid},
        }
    )
    out_obj: dict[str, Any] = {
        "status": "sent",
        "signal_id": sid,
        "paper": paper_flag,
        "broker_response": body[:2000],
    }
    if broker_parsed:
        for k in ("ib_order_id", "qty", "ticker", "action", "notional_usd", "ref_price", "mode"):
            if k in broker_parsed:
                out_obj[k] = broker_parsed[k]
    return json.dumps(out_obj, ensure_ascii=False)


def register_quant_trader_skills(db: Any, llm: Any, tools: list[Any]) -> None:
    from langchain_core.tools import StructuredTool

    def _fetch_market_data(ticker: str, timeframe: str = "1d", lookback_days: int = 365) -> str:
        raw = _fetch_market_data_impl(
            db,
            ticker=ticker,
            timeframe=timeframe,
            lookback_days=int(lookback_days),
        )
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("status") == "ok":
                tkr = str(payload.get("ticker") or ticker or "").strip().upper()
                if tkr:
                    note_quant_market_evidence_ticker(tkr)
        except (json.JSONDecodeError, TypeError):
            pass
        return raw

    def _fetch_ib_gateway_ohlcv(
        ticker: str, timeframe: str = "1h", lookback_days: int = 20
    ) -> str:
        raw = _fetch_ib_gateway_ohlcv_impl(
            db,
            ticker=ticker,
            timeframe=timeframe,
            lookback_days=int(lookback_days),
        )
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("status") == "ok":
                tkr = str(payload.get("ticker") or ticker or "").strip().upper()
                if tkr:
                    note_quant_market_evidence_ticker(tkr)
        except (json.JSONDecodeError, TypeError):
            pass
        return raw

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

    def _evaluate_cfd_state(
        session_uid: str,
        tickers: list[str],
        signal_threshold: str = "GAS",
    ) -> str:
        return _evaluate_cfd_state_impl(
            db,
            session_uid=session_uid,
            tickers=tickers,
            signal_threshold=signal_threshold,
        )

    tools.append(
        StructuredTool.from_function(
            _fetch_market_data,
            name="fetch_market_data",
            description="Obtiene OHLCV y persiste en quant_core.ohlcv_data para evidencia del turno.",
        )
    )
    tools.append(
        StructuredTool.from_function(
            _fetch_ib_gateway_ohlcv,
            name="fetch_ib_gateway_ohlcv",
            description=(
                "OHLCV solo desde IB Gateway vía HTTP (GET /api/market/ibkr/historical; requiere "
                "IBKR_GATEWAY_OHLCV_URL en el proceso del gateway). No usa lake SSH. Persiste en "
                "quant_core.ohlcv_data como evidencia. Parámetros típicos: timeframe 1h/30m/1d; "
                "lookback_days ventana en días (hasta ~4000), p. ej. SPY timeframe=1h lookback_days=20."
            ),
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
                "Propone una senal en finance_worker.trade_signals via StateDelta; aplica EvidenceUnique y RiskGuard. "
                "Devuelve signal_id (UUID): cit ese valor literal en la respuesta al usuario y la linea "
                "`/execute_signal <signal_id>` para HITL."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute_approved_signal,
            name="execute_approved_signal",
            description=(
                "Ejecuta una senal tras HITL usando el mismo signal_id (UUID) que devolvio propose_trade_signal. "
                "Requiere human_approved o /execute_signal <signal_id> en Telegram. "
                "El modo paper/live del POST al broker sigue quant_core.trading_sessions (id=active) y debe alinear "
                "con IBKR_ACCOUNT_MODE; se envia cabecera X-Duckclaw-IBKR-Account-Mode (paper|live). "
                "La respuesta puede incluir campos del broker (p. ej. ib_order_id, qty); citarlos literalmente; "
                "no es lo mismo que get_ibkr_portfolio (IBKR_PORTFOLIO_API_URL), que es snapshot aparte."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _evaluate_cfd_state,
            name="evaluate_cfd_state",
            description=(
                "Evalúa el estado CFD de la sesión activa en un solo paso: valida sesión ACTIVE, "
                "ingesta OHLCV por ticker, calcula temperatura/mass/fase, persiste fluid_state y "
                "retorna outcome ALIGNED/MISALIGNED más gating de pending HITL."
            ),
        )
    )
