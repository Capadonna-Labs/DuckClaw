"""Skills del worker Quant Trader (StateDelta + RiskGuard + HITL)."""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.request
import uuid
import base64
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from duckclaw.forge.skills.ibkr_bridge import (
    _ibkr_resolve_payload_with_optional_alt,
    fetch_ibkr_total_equity_numeric,
)
from duckclaw.forge.skills.quant_market_bridge import (
    _fetch_ib_gateway_ohlcv_impl,
    _fetch_market_data_impl,
)
from duckclaw.forge.skills.quant_cfd_bridge import _record_fluid_state_impl
from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync
from duckclaw.forge.skills.intraday_accum_window import inside_reference_equity_rth_cot
from duckclaw.forge.skills.quant_hitl import consume_execute_order_grant, grant_execute_order
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


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _auto_execute_wait_timeout_sec() -> float:
    raw = (os.environ.get("DUCKCLAW_QUANT_AUTO_EXECUTE_WAIT_SEC") or "5").strip()
    try:
        t = float(raw)
    except ValueError:
        t = 5.0
    return max(0.2, min(t, 60.0))


def _quant_auto_execute_allowed_for_session_mode(db: Any) -> bool:
    """Auto-ejecución: paper por defecto; live requiere DUCKCLAW_QUANT_AUTO_EXECUTE_ALLOW_LIVE."""
    m = _trading_session_mode(db)
    if m == "paper":
        return True
    if m == "live":
        return _env_truthy("DUCKCLAW_QUANT_AUTO_EXECUTE_ALLOW_LIVE")
    return True


def _quant_now_bogota() -> datetime:
    """Momento efectivo para gating auto-ejecución MOC (tests monkeypatch)."""
    try:
        return datetime.now(ZoneInfo("America/Bogota"))
    except Exception:
        return datetime.now(timezone.utc)


def _quant_ignore_moc_time_gates() -> bool:
    """Dev/CI: omitir ventana MOC para auto-exec encadenada (evitar en prod)."""
    return _env_truthy("DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES") or _env_truthy(
        "DUCKCLAW_QUANT_AUTO_EXECUTE_IGNORE_MOC_WINDOW"
    )


def _quant_block_non_moc_ledger_creation() -> bool:
    """
    Opt-in legado: si es verdadero, `propose_trade_signal` con strategy distinto de
    `moc_hrp_cfd` solo crea filas Ledger dentro de la ventana MOC (comportamiento antiguo).
    Default: permitir propuesta en cualquier horario lun–vie; la auto-exec sigue acotada a MOC.
    """
    return _env_truthy("DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER")


def _quant_auto_execute_inside_moc_window() -> tuple[bool, str, dict[str, Any]]:
    """
    Lun–vie America/Bogota dentro de DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW.

    Default 14:40:00–14:59:30 COT (véase duckclaw.forge.skills.moc_execution_window).

    Usado por: cadena auto-exec con DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS (y opt-in
    DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER para bloquear también la creación ledger).

    Bypass: DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES o DUCKCLAW_QUANT_AUTO_EXECUTE_IGNORE_MOC_WINDOW=1.
    """
    if _quant_ignore_moc_time_gates():
        return True, "", {}

    from duckclaw.forge.skills.moc_execution_window import parse_moc_execution_window_bounds

    now = _quant_now_bogota()
    start_s, end_s, win_label = parse_moc_execution_window_bounds()
    meta: dict[str, Any] = {
        "window": f"{win_label} America/Bogota (lun-vie)",
        "local_iso": now.date().isoformat() + "T" + now.strftime("%H:%M:%S"),
    }

    if now.weekday() >= 5:
        return False, "WEEKEND", meta

    cur_s = now.hour * 3600 + now.minute * 60 + int(now.second)
    if cur_s < start_s or cur_s > end_s:
        return False, "OUTSIDE_MOC_WINDOW", meta

    return True, "", meta


def _wait_until_signal_row_visible(db: Any, signal_id: str, *, timeout_sec: float) -> bool:
    """
    Tras encolar StateDelta, el db-writer persiste con latencia. Poll hasta que la fila exista o timeout.

    Con DuckDB, un handle RO mantiene lock de archivo: el db-writer no puede escribir la fila
    mientras el gateway tenga la conexión abierta. Entre cada intento, suspendemos el RO
    (mismo criterio que read_sql) para ceder el archivo al writer, luego reabrimos y consultamos.
    """
    sid = (signal_id or "").strip()
    if not sid:
        return False
    deadline = time.time() + float(timeout_sec)
    esc = sid.replace("'", "''")
    q = (
        "SELECT 1 AS ok FROM finance_worker.trade_signals WHERE signal_id='"
        + esc
        + "' LIMIT 1"
    )
    step = 0.05
    susp = getattr(db, "suspend_readonly_file_handle", None)
    resu = getattr(db, "resume_readonly_file_handle", None)
    ro = bool(getattr(db, "_read_only", False))
    release_each_iter = ro and callable(susp) and callable(resu)
    iteration = 0
    t0 = time.time()
    while time.time() < deadline:
        iteration += 1
        if release_each_iter:
            try:
                susp()
            except Exception:
                pass
            time.sleep(step)
            try:
                resu()
            except Exception:
                pass
        try:
            raw = db.query(q)
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            rows = []
        if rows and isinstance(rows[0], dict):
            return True
        if not release_each_iter:
            time.sleep(step)
    return False


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


def _coerce_positive_weight(value: Any) -> Optional[float]:
    """Convierte peso a float positivo finito; acepta strings con '%'."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip().replace("%", "")
        if not s:
            return None
        try:
            v = float(s)
        except ValueError:
            return None
    else:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
    if not math.isfinite(v) or v <= 0:
        return None
    return _normalize_proposed_weight_pct(v)


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


_INTRADAY_MOC_ACCUM_PATCH_KEYS = frozenset({"weight_scale", "weight_scale_max", "force_hold", "notes"})


def _sanitize_intraday_accum_patch(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): v for k, v in raw.items() if str(k) in _INTRADAY_MOC_ACCUM_PATCH_KEYS
    }


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
        "y si hay setup válido propón señal con `propose_trade_signal` (tras evidencia OHLCV del ticker); "
        "la propuesta ledger puede crearse en cualquier horario; la **auto-ejecución** encadenada "
        "(env `DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS`) sigue solo dentro de ventana MOC COT "
        "(default 14:40:00–14:59:30). Para restaurar bloqueo de propuesta fuera de MOC: "
        "`DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER=1` → error `OUTSIDE_MOC_PREP_WINDOW`. "
        "Durante lun–vie 08:30–15:00 COT, sesión ACTIVE, opcional hints sin ledger via "
        "`accumulate_moc_intraday_state` (merge cola hasta MOC calc PM2; no substituye `propose_trade_signal`)."
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
        },
        duckclaw_db=db,
    )


def _signal_id_looks_placeholder(sid: str) -> bool:
    """Heurística: UUIDs que el LLM suele inventar (no existen en trade_signals)."""
    s = (sid or "").strip().lower()
    if not s:
        return False
    return bool(
        s.startswith("9999")
        or s.startswith("00000000")
        or "ffff" in s
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
        # Carpeta de plantilla es Quant-Trader/; "quant_trader" no existe → política por defecto sin montajes RO.
        worker_id="Quant-Trader",
    )
    payload = {
        "exit_code": int(result.exit_code),
        "stdout": (result.stdout or "")[:8000],
        "stderr": (result.stderr or "")[:4000],
    }
    if result.artifacts:
        payload["artifacts"] = result.artifacts
        # No inyectar figure_base64 completo al contexto del LLM (puede disparar >100k tokens).
        # El manager extrae la imagen desde artifacts (ruta local) y la envía por Telegram.
    if int(result.exit_code) != 0:
        payload["error"] = "SANDBOX_EXECUTION_FAILED"
    return json.dumps(payload, ensure_ascii=False)


def _hrp_collect_price_series_from_ib_gateway(
    db: Any,
    *,
    tickers: list[str],
    timeframe: str,
    lookback_days: int,
) -> tuple[dict[str, list[float]], list[dict[str, Any]]]:
    series: dict[str, list[float]] = {}
    ingest: list[dict[str, Any]] = []
    for tkr in tickers:
        raw = _fetch_ib_gateway_ohlcv_impl(
            db,
            ticker=tkr,
            timeframe=timeframe,
            lookback_days=int(lookback_days),
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": "invalid_json", "raw": raw[:800]}
        ingest.append({"ticker": tkr, "result": payload})
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            continue
        note_quant_market_evidence_ticker(tkr)
        esc = tkr.replace("'", "''")
        q = (
            "SELECT close FROM quant_core.ohlcv_data "
            f"WHERE ticker = '{esc}' ORDER BY timestamp DESC LIMIT 800"
        )
        try:
            rows_raw = db.query(q)
            rows = json.loads(rows_raw) if isinstance(rows_raw, str) else (rows_raw or [])
        except Exception:
            rows = []
        closes: list[float] = []
        for row in reversed(rows):
            if not isinstance(row, dict):
                continue
            try:
                c = float(row.get("close"))
            except (TypeError, ValueError):
                continue
            if c > 0:
                closes.append(c)
        if len(closes) >= 4:
            series[tkr] = closes
    return series, ingest


def _hrp_current_weights_from_ibkr(tickers: list[str]) -> tuple[dict[str, float], dict[str, Any]]:
    api_url = (os.environ.get("IBKR_PORTFOLIO_API_URL") or "").strip()
    api_key = (os.environ.get("IBKR_PORTFOLIO_API_KEY") or "").strip()
    positions_url = (os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL") or "").strip()
    if not api_url or not api_key:
        return ({t: 0.0 for t in tickers}, {"warning": "IBKR_PORTFOLIO_API_URL/KEY no configurados."})
    try:
        data, effective_mode, configured_mode = _ibkr_resolve_payload_with_optional_alt(
            api_url, api_key, positions_url
        )
    except Exception as exc:
        return ({t: 0.0 for t in tickers}, {"warning": f"No se pudo leer portafolio IBKR: {str(exc)[:300]}"})
    if not isinstance(data, dict):
        return ({t: 0.0 for t in tickers}, {"warning": "Snapshot IBKR inválido (no dict)."})
    portfolio = data.get("portfolio") or data.get("positions") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []
    total_value = data.get("total_value")
    if total_value is None:
        total_value = data.get("net_liquidation") or data.get("equity") or data.get("value") or 0
    try:
        total_f = float(total_value)
    except (TypeError, ValueError):
        total_f = 0.0
    if total_f <= 0 and isinstance(portfolio, list):
        for pos in portfolio:
            if not isinstance(pos, dict):
                continue
            mv = pos.get("market_value") or pos.get("marketValue") or pos.get("value") or 0
            try:
                total_f += max(0.0, float(mv))
            except (TypeError, ValueError):
                continue
    requested = {t.upper() for t in tickers}
    alloc: dict[str, float] = {t: 0.0 for t in requested}
    if isinstance(portfolio, list):
        for pos in portfolio:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or pos.get("ticker") or "").strip().upper()
            if not sym or sym not in requested:
                continue
            mv = pos.get("market_value") or pos.get("marketValue") or pos.get("value") or 0
            try:
                alloc[sym] += max(0.0, float(mv))
            except (TypeError, ValueError):
                continue
    if total_f > 0:
        weights = {t: float(alloc.get(t, 0.0)) / total_f for t in requested}
    else:
        weights = {t: 0.0 for t in requested}
    return (
        weights,
        {
            "configured_mode": configured_mode,
            "effective_mode": effective_mode,
            "total_value": total_f,
        },
    )


def _build_hrp_sandbox_script(
    *,
    price_series: dict[str, list[float]],
    current_weights: dict[str, float],
    threshold: float,
) -> str:
    return f"""
import json
import numpy as np
import pandas as pd

PRICE_SERIES = {json.dumps(price_series, ensure_ascii=False)}
CURRENT_WEIGHTS = {json.dumps(current_weights, ensure_ascii=False)}
REBALANCE_THRESHOLD = {float(threshold)}

def _normalize(weights):
    clipped = {{k: max(float(v), 0.0) for k, v in weights.items()}}
    total = float(sum(clipped.values()))
    if total <= 0:
        n = max(1, len(clipped))
        return {{k: 1.0 / n for k in clipped}}
    return {{k: v / total for k, v in clipped.items()}}

def _manual_hrp(returns_df):
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    cov = returns_df.cov()
    corr = returns_df.corr().fillna(0.0)
    dist = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    order_idx = leaves_list(linkage(squareform(dist, checks=False), method="single")).tolist()
    tickers = [cov.columns[int(i)] for i in order_idx]
    cov_diag = np.diag(cov.loc[tickers, tickers].values)
    inv_var = np.where(cov_diag > 0, 1.0 / cov_diag, 0.0)
    if float(inv_var.sum()) <= 0:
        raw = {{t: 1.0 for t in tickers}}
    else:
        raw = {{t: float(inv_var[i]) for i, t in enumerate(tickers)}}
    return _normalize(raw)

def _compute_hrp(returns_df):
    try:
        from pypfopt import HRPOpt, risk_models
        cov = risk_models.sample_cov(returns_df)
        hrp = HRPOpt(returns=returns_df, cov_matrix=cov)
        return _normalize(hrp.optimize()), "pypfopt"
    except Exception:
        return _manual_hrp(returns_df), "manual_scipy"

prices = pd.DataFrame(PRICE_SERIES).apply(pd.to_numeric, errors="coerce").dropna(how="any")
if prices.shape[0] < 4 or prices.shape[1] < 2:
    print(json.dumps({{"ok": False, "error": "Datos insuficientes para HRP (min 4 filas, 2 activos)."}}, ensure_ascii=False))
    raise SystemExit(0)

returns_df = prices.pct_change().dropna(how="any")
targets, method = _compute_hrp(returns_df)
tickers = sorted(targets.keys())
current = _normalize({{t: float(CURRENT_WEIGHTS.get(t, 0.0)) for t in tickers}})
deltas = {{t: float(targets[t] - current.get(t, 0.0)) for t in tickers}}
max_abs_delta = max(abs(v) for v in deltas.values()) if deltas else 0.0

print(json.dumps({{
    "ok": True,
    "method": method,
    "tickers": tickers,
    "target_weights": targets,
    "current_weights": current,
    "weight_deltas": deltas,
    "max_abs_delta": max_abs_delta,
    "rebalance_required": bool(max_abs_delta >= REBALANCE_THRESHOLD),
    "threshold": REBALANCE_THRESHOLD,
    "n_obs": int(returns_df.shape[0]),
}}, ensure_ascii=False))
""".strip()


@log_tool_execution_sync(name="hrp_rebalance_ib_gateway")
def _hrp_rebalance_ib_gateway_impl(
    db: Any,
    llm: Any,
    *,
    tickers: list[str],
    timeframe: str = "1h",
    lookback_days: int = 30,
    rebalance_threshold: float = 0.03,
) -> str:
    del llm
    tk = [str(t or "").strip().upper() for t in (tickers or []) if str(t or "").strip()]
    tk = list(dict.fromkeys(tk))
    if len(tk) < 2:
        return json.dumps({"error": "Debes enviar al menos 2 tickers."}, ensure_ascii=False)
    prices, ingest = _hrp_collect_price_series_from_ib_gateway(
        db, tickers=tk, timeframe=timeframe, lookback_days=int(lookback_days)
    )
    if len(prices) < 2:
        return json.dumps(
            {
                "error": "INSUFFICIENT_OHLCV",
                "message": "No se obtuvieron series válidas desde IB Gateway para al menos 2 tickers.",
                "ingest": ingest,
            },
            ensure_ascii=False,
        )
    ib_weights, ib_meta = _hrp_current_weights_from_ibkr(list(prices.keys()))
    code = _build_hrp_sandbox_script(
        price_series=prices,
        current_weights=ib_weights,
        threshold=float(max(0.0001, rebalance_threshold)),
    )
    result = run_in_sandbox(
        db=db,
        llm=None,
        code=code,
        language="python",
        original_request="hrp rebalance from ib_gateway",
        max_retries=1,
        worker_id="Quant-Trader",
    )
    out: dict[str, Any] = {
        "exit_code": int(result.exit_code),
        "stderr": (result.stderr or "")[:2000],
        "ingest": ingest,
        "ibkr_meta": ib_meta,
    }
    if int(result.exit_code) != 0:
        out["error"] = "SANDBOX_EXECUTION_FAILED"
        out["stdout"] = (result.stdout or "")[:3000]
        return json.dumps(out, ensure_ascii=False)
    parsed: dict[str, Any] | None = None
    for line in reversed((result.stdout or "").splitlines()):
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed = obj
            break
    out["result"] = parsed or {"ok": False, "error": "No se pudo parsear JSON de sandbox."}
    return json.dumps(out, ensure_ascii=False)


@log_tool_execution_sync(name="accumulate_moc_intraday_state")
def _accumulate_moc_intraday_state_impl(
    db: Any,
    *,
    ticker: str,
    accumulation_patch: dict[str, Any] | None = None,
    trading_date: str = "",
) -> str:
    """
    Encola UPSERT shallow en quant_core.intraday_moc_accum (delta INTRADAY_MOC_ACCUM_UPSERT).
    No crea trade_signals ni HITL; PM2 puede fusionar hints en calc.
    """
    tkr = (ticker or "").strip().upper()
    if not tkr:
        return json.dumps({"error": "ticker requerido"}, ensure_ascii=False)

    if _quant_ignore_moc_time_gates():
        ok_rth, rth_reason, rth_meta = True, "", {}
    else:
        ok_rth, rth_reason, rth_meta = inside_reference_equity_rth_cot()
    if not ok_rth:
        return json.dumps(
            {
                "error": "OUTSIDE_REFERENCE_RTH_ACCUM_WINDOW",
                "reason": rth_reason,
                "message": (
                    "Solo lun–vie 08:30–15:00 America/Bogota (spec ref. RTH COT); "
                    "dev: DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES."
                ),
                **rth_meta,
            },
            ensure_ascii=False,
        )

    sess = _active_session_snapshot(db)
    if not sess or str(sess.get("status") or "").strip().upper() != "ACTIVE":
        return json.dumps(
            {"error": "NO_ACTIVE_TRADING_SESSION", "message": "quant_core.trading_sessions id=active no ACTIVE"},
            ensure_ascii=False,
        )
    uid = str(sess.get("session_uid") or "").strip()
    if not uid:
        return json.dumps({"error": "SESSION_UID_MISSING", "message": "La sesión activa carece session_uid"}, ensure_ascii=False)

    tickers_allow = [
        x.strip().upper() for x in str(sess.get("tickers") or "").split(",") if x.strip()
    ]
    if tickers_allow and tkr not in tickers_allow:
        return json.dumps(
            {
                "error": "TICKER_NOT_IN_SESSION_ALLOWLIST",
                "message": f"{tkr} no está entre tickers de la sesión activa.",
                "allowed": tickers_allow,
            },
            ensure_ascii=False,
        )

    patch_s = _sanitize_intraday_accum_patch(accumulation_patch)
    if not patch_s:
        return json.dumps(
            {"error": "EMPTY_PATCH", "message": "Envía una o más claves: weight_scale, weight_scale_max, force_hold, notes"},
            ensure_ascii=False,
        )

    base = _state_delta_base()
    if not base["target_db_path"]:
        try:
            base["target_db_path"] = str(getattr(db, "_path", "") or "")
        except Exception:
            base["target_db_path"] = ""
    if not base["target_db_path"]:
        return json.dumps({"error": "target_db_path no resuelto para StateDelta"}, ensure_ascii=False)

    td_trim = str(trading_date or "").strip()
    mut: dict[str, Any] = {"session_uid": uid, "ticker": tkr, "patch": patch_s}
    if td_trim:
        mut["trading_date"] = td_trim[:16]

    ok = push_quant_state_delta_sync(
        {**base, "delta_type": "INTRADAY_MOC_ACCUM_UPSERT", "mutation": mut},
        duckclaw_db=db,
    )
    if not ok:
        return json.dumps({"error": "enqueue_failed", "message": "No se encoló INTRADAY_MOC_ACCUM_UPSERT (Redis?)"}, ensure_ascii=False)

    return json.dumps(
        {
            "status": "enqueued",
            "session_uid": uid,
            "ticker": tkr,
            "patch": patch_s,
            **({"trading_date": td_trim} if td_trim else {}),
            "hint": "El db-writer hace UPSERT; PM2 aplicará hints en calc salvo finalized_at.",
        },
        ensure_ascii=False,
    )


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
    strategy_name: str = "cfd_auto",
    session_uid_override: str = "",
) -> str:
    tkr = (ticker or "").strip().upper()
    mid_in = (mandate_id or "").strip()
    mid = str(uuid.uuid4()) if not mid_in else _coerce_mandate_id_to_uuid(mid_in)
    if not tkr:
        return json.dumps({"error": "ticker requerido"}, ensure_ascii=False)

    strat_eff = (strategy_name or "cfd_auto").strip() or "cfd_auto"
    if strat_eff != "moc_hrp_cfd" and _quant_block_non_moc_ledger_creation():
        ok_gate, gate_reason, gate_meta = _quant_auto_execute_inside_moc_window()
        if not ok_gate:
            prep_hint = (
                "Fase preparación (overnight gap squeeze / CFD): recolecta contexto con "
                "evaluate_cfd_state, fetch_market_data, fetch_ib_gateway_ohlcv, read_sql, get_ibkr_portfolio; "
                "no invoques propose_trade_signal hasta la ventana MOC (default 14:40:00–14:59:30 COT; env DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW). "
                "Sin este bloqueo: quita DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER."
            )
            return json.dumps(
                {
                    "error": "OUTSIDE_MOC_PREP_WINDOW",
                    "reason": gate_reason,
                    "message": (
                        f"Fuera de ventana MOC ({gate_meta.get('window', '')}): no se crean señales Ledger "
                        f"(DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER). "
                        + ("Fin de semana. " if gate_reason == "WEEKEND" else "")
                        + prep_hint
                    ),
                    **gate_meta,
                },
                ensure_ascii=False,
            )

    has_evidence = has_quant_market_evidence_for_ticker(tkr)
    if not has_evidence:
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
    st_up = str(signal_type or "").strip().upper()
    if not math.isfinite(w):
        return json.dumps({"error": "weight inválido"}, ensure_ascii=False)
    if w <= 0:
        if st_up == "EXIT":
            w = 0.01  # nominal % para ledger EXIT (p. ej. MOC rebalance-down)
        else:
            return json.dumps({"error": "weight inválido (debe ser > 0 y finito)"}, ensure_ascii=False)
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
    session_uid = str((session_uid_override or "").strip() or (sess.get("session_uid") or "")).strip()
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
        },
        duckclaw_db=db,
    )
    ok_s = push_quant_state_delta_sync(
        {
            **base,
            "delta_type": "TRADE_SIGNAL_PROPOSED",
            "mutation": {
                "signal_id": signal_id,
                "mandate_id": mid,
                "ticker": tkr,
                "signal_type": "ENTRY" if st_up != "EXIT" else "EXIT",
                "proposed_weight": float(guarded),
                "sandbox_backtest_cid": (sandbox_backtest_cid or "").strip(),
                "human_approved": False,
                "status": "PENDING_HITL",
                "rationale": rr,
                "session_uid": session_uid,
                "strategy_name": (strategy_name or "cfd_auto").strip() or "cfd_auto",
            },
        },
        duckclaw_db=db,
    )
    if not (ok_m and ok_s):
        return json.dumps({"error": "No se pudo encolar StateDelta en Redis"}, ensure_ascii=False)

    out: dict[str, Any] = {
        "status": "PENDING_HITL",
        "session_uid": session_uid,
        "signal_id": signal_id,
        "mandate_id": mid,
        "ticker": tkr,
        "proposed_weight": guarded,
        "liquid_capital": cap,
        "hint": f"Senal {signal_id} lista. Requiere /execute_signal {signal_id}",
    }

    strat = strat_eff
    moc_batch_auto = strat == "moc_hrp_cfd" and _env_truthy("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE") and _env_truthy(
        "DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS"
    )
    if strat == "moc_hrp_cfd" and not moc_batch_auto:
        return json.dumps(out, ensure_ascii=False)

    if not _env_truthy("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS"):
        return json.dumps(out, ensure_ascii=False)
    if not _quant_auto_execute_allowed_for_session_mode(db):
        out["auto_execute"] = {
            "skipped": True,
            "reason": "LIVE_SESSION_REQUIRES_ALLOW_LIVE",
            "message": (
                "Sesión live: define DUCKCLAW_QUANT_AUTO_EXECUTE_ALLOW_LIVE=1 para auto-ejecutar; "
                "o aprueba con /execute_signal y execute_approved_signal."
            ),
        }
        return json.dumps(out, ensure_ascii=False)

    ok_moc, moc_reason, moc_meta = _quant_auto_execute_inside_moc_window()
    if not ok_moc:
        msg_parts = [
            "Auto-ejecución encadenada solo dentro de ventana MOC configurada ",
            f"({moc_meta.get('window', '')}); fuera usa /execute_signal <uuid>.",
        ]
        if moc_reason == "WEEKEND":
            msg_parts.insert(0, "Fin de semana: ")
        out["auto_execute"] = {
            "skipped": True,
            "reason": moc_reason,
            "message": "".join(msg_parts),
            **moc_meta,
        }
        return json.dumps(out, ensure_ascii=False)

    wait_to = _auto_execute_wait_timeout_sec()
    if not _wait_until_signal_row_visible(db, signal_id, timeout_sec=wait_to):
        out["auto_execute"] = {
            "error": "SIGNAL_ROW_TIMEOUT",
            "message": (
                f"La señal aún no estaba en DuckDB tras {wait_to:.1f}s (db-writer). "
                "Aprobación manual con /execute_signal sigue disponible."
            ),
        }
        return json.dumps(out, ensure_ascii=False)

    cid = get_quant_tool_chat_id() or "default"
    grant_execute_order(cid, signal_id)
    exec_raw = _execute_approved_signal_impl(
        db,
        signal_id=signal_id,
        override_order_payload={
            "ticker": tkr,
            "signal_type": "ENTRY" if str(signal_type).upper() != "EXIT" else "EXIT",
            "proposed_weight": float(guarded),
            "mandate_id": mid,
        },
    )
    exec_obj: Any = exec_raw
    try:
        if isinstance(exec_raw, str) and exec_raw.strip().startswith("{"):
            exec_obj = json.loads(exec_raw)
    except json.JSONDecodeError:
        pass
    out["auto_executed"] = True
    out["execution"] = exec_obj
    if isinstance(exec_obj, dict) and str(exec_obj.get("status") or "").lower() in ("sent", "simulated"):
        out["hint"] = f"Auto-ejecutada signal_id={signal_id}. Revisa execution para broker/ib_order_id."
    return json.dumps(out, ensure_ascii=False)


@log_tool_execution_sync(name="execute_approved_signal")
def _execute_approved_signal_impl(
    db: Any,
    *,
    signal_id: str,
    override_order_payload: Optional[dict[str, Any]] = None,
) -> str:
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
        return json.dumps(
            {
                "error": "signal no existe",
                "reason": "SIGNAL_ID_NOT_IN_LEDGER",
                "message": (
                    "Este signal_id no está en finance_worker.trade_signals. "
                    "No inventes UUIDs: primero propose_trade_signal (el signal_id sale en el JSON de la tool) "
                    "o usa el uuid de una señal PENDING listada con read_sql; luego /execute_signal o otra llamada "
                    "a execute_approved_signal."
                ),
            },
            ensure_ascii=False,
        )
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
    if not url:
        push_quant_state_delta_sync(
            {
                **_state_delta_base(),
                "target_db_path": tgt,
                "delta_type": "TRADE_SIGNAL_EXECUTED",
                "mutation": {"signal_id": sid},
            },
            duckclaw_db=db,
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
    ov = override_order_payload if isinstance(override_order_payload, dict) else {}
    post: dict[str, Any] = {"signal_id": sid, "paper": paper_flag}
    tkr = str(sig_row.get("ticker") or ov.get("ticker") or "").strip().upper()
    if tkr:
        post["ticker"] = tkr
    st = str(sig_row.get("signal_type") or ov.get("signal_type") or "").strip().upper()
    if st in ("ENTRY", "EXIT"):
        post["signal_type"] = st
    pw_source = "none"
    pw_row = _coerce_positive_weight(sig_row.get("proposed_weight"))
    if pw_row is not None:
        post["proposed_weight"] = pw_row
        pw_source = "db_row"
    if "proposed_weight" not in post:
        pw_override = _coerce_positive_weight(ov.get("proposed_weight"))
        if pw_override is not None:
            post["proposed_weight"] = pw_override
            pw_source = "override"
    mid = str(sig_row.get("mandate_id") or ov.get("mandate_id") or "").strip()
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
    released_ro_for_broker = False
    susp = getattr(db, "suspend_readonly_file_handle", None)
    resu = getattr(db, "resume_readonly_file_handle", None)
    ro = bool(getattr(db, "_read_only", False))
    if ro and callable(susp) and callable(resu):
        try:
            susp()
            released_ro_for_broker = True
        except Exception:
            released_ro_for_broker = False
    try:
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
    finally:
        if released_ro_for_broker and callable(resu):
            try:
                resu()
            except Exception:
                pass

    try:
        if body.strip().startswith("{"):
            _bp = json.loads(body)
            if isinstance(_bp, dict):
                broker_parsed = _bp
    except json.JSONDecodeError:
        broker_parsed = {}
    push_quant_state_delta_sync(
        {
            **_state_delta_base(),
            "target_db_path": tgt,
            "delta_type": "TRADE_SIGNAL_EXECUTED",
            "mutation": {"signal_id": sid},
        },
        duckclaw_db=db,
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


@log_tool_execution_sync(name="run_quant_signal_cycle")
def _run_quant_signal_cycle_impl(
    db: Any,
    *,
    mandate_id: str,
    ticker: str,
    weight: float,
    rationale: str = "",
    signal_type: str = "ENTRY",
    execute_now: bool = False,
) -> str:
    """
    Operación compuesta determinista:
    1) propose_trade_signal
    2) opcional execute_approved_signal con el signal_id real del ledger.
    """
    proposed_raw = _propose_trade_signal_impl(
        db,
        mandate_id=mandate_id,
        ticker=ticker,
        weight=weight,
        rationale=rationale,
        signal_type=signal_type,
    )
    try:
        proposed_obj = json.loads(proposed_raw) if isinstance(proposed_raw, str) else proposed_raw
    except Exception:
        proposed_obj = {"raw": str(proposed_raw)}
    if not isinstance(proposed_obj, dict):
        return json.dumps({"error": "INVALID_PROPOSE_RESPONSE", "proposed": proposed_obj}, ensure_ascii=False)
    if proposed_obj.get("error"):
        return json.dumps({"status": "failed", "proposed": proposed_obj}, ensure_ascii=False)
    sid = str(proposed_obj.get("signal_id") or "").strip().lower()
    if not sid:
        return json.dumps(
            {
                "status": "failed",
                "error": "MISSING_SIGNAL_ID",
                "message": "propose_trade_signal no devolvió signal_id.",
                "proposed": proposed_obj,
            },
            ensure_ascii=False,
        )
    out: dict[str, Any] = {
        "status": "proposed",
        "signal_id": sid,
        "proposed": proposed_obj,
    }
    if not execute_now:
        return json.dumps(out, ensure_ascii=False)
    if bool(proposed_obj.get("auto_executed")) and proposed_obj.get("execution") is not None:
        exec_obj = proposed_obj.get("execution")
        out["execution"] = exec_obj
        out["execution_source"] = "propose_auto_execute"
        if isinstance(exec_obj, dict) and exec_obj.get("error"):
            out["status"] = "execution_failed"
        else:
            out["status"] = "executed"
        return json.dumps(out, ensure_ascii=False)
    exec_raw = _execute_approved_signal_impl(
        db,
        signal_id=sid,
        override_order_payload={
            "ticker": str(proposed_obj.get("ticker") or ticker or "").strip().upper(),
            "signal_type": str(proposed_obj.get("signal_type") or signal_type or "ENTRY").strip().upper(),
            "proposed_weight": proposed_obj.get("proposed_weight"),
            "mandate_id": str(proposed_obj.get("mandate_id") or mandate_id or "").strip(),
        },
    )
    try:
        exec_obj = json.loads(exec_raw) if isinstance(exec_raw, str) else exec_raw
    except Exception:
        exec_obj = {"raw": str(exec_raw)}
    out["execution"] = exec_obj
    if isinstance(exec_obj, dict) and exec_obj.get("error"):
        out["status"] = "execution_failed"
    else:
        out["status"] = "executed"
    return json.dumps(out, ensure_ascii=False)


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

    def _hrp_rebalance_ib_gateway(
        tickers: list[str],
        timeframe: str = "1h",
        lookback_days: int = 30,
        rebalance_threshold: float = 0.03,
    ) -> str:
        return _hrp_rebalance_ib_gateway_impl(
            db,
            llm,
            tickers=tickers,
            timeframe=timeframe,
            lookback_days=int(lookback_days),
            rebalance_threshold=float(rebalance_threshold),
        )

    def _accumulate_moc_intraday_state(
        ticker: str,
        accumulation_patch: dict[str, Any] | None = None,
        trading_date: str = "",
    ) -> str:
        return _accumulate_moc_intraday_state_impl(
            db,
            ticker=ticker,
            accumulation_patch=accumulation_patch,
            trading_date=str(trading_date or "").strip(),
        )

    def _propose_trade_signal(
        mandate_id: str,
        ticker: str,
        weight: float,
        rationale: str = "",
        signal_type: str = "ENTRY",
        sandbox_backtest_cid: str = "",
        strategy_name: str = "cfd_auto",
    ) -> str:
        return _propose_trade_signal_impl(
            db,
            mandate_id=mandate_id,
            ticker=ticker,
            weight=weight,
            rationale=rationale,
            signal_type=signal_type,
            sandbox_backtest_cid=sandbox_backtest_cid,
            strategy_name=strategy_name,
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

    def _run_quant_signal_cycle(
        mandate_id: str,
        ticker: str,
        weight: float,
        rationale: str = "",
        signal_type: str = "ENTRY",
        execute_now: bool = False,
    ) -> str:
        return _run_quant_signal_cycle_impl(
            db,
            mandate_id=mandate_id,
            ticker=ticker,
            weight=weight,
            rationale=rationale,
            signal_type=signal_type,
            execute_now=bool(execute_now),
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
                "OHLCV que persiste en quant_core.ohlcv_data. Orden efectivo: 1) lake SSH si el timeframe está en "
                "CAPADONNA_HISTORICAL_TIMEFRAMES y fuera del solape IBKR_REALTIME_TIMEFRAMES (misma regla que "
                "fetch_market_data); 2) IBKR_MARKET_DATA_URL si está definido y responde ok; "
                "3) IBKR_GATEWAY_OHLCV_URL (GET /api/market/ibkr/historical) como último recurso. "
                "Parámetros típicos: timeframe 1h/30m/1d; lookback_days hasta ~4000."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute_sandbox_script,
            name="execute_sandbox_script",
            description=(
                "Ejecuta Python en contenedor Strix (Docker). Imagen duckclaw/sandbox:latest "
                "(docker/sandbox/Dockerfile): pandas, scipy, sklearn, PyPortfolioOpt (pypfopt), matplotlib, duckdb, "
                "ML4T diagnostic+backtest (import ml4t.diagnostic / ml4t.backtest) — sin ml4t-data remoto; "
                "series vienen de fetch_market_data/fetch_ib_gateway_ohlcv/read_sql en el host o /workspace/data RO. "
                "Prohibido rotular salida «ML4T …» sin import real. "
                "Timeout según Quant-Trader/security_policy.yaml. Requiere Docker y STRIX_SANDBOX_IMAGE opcional."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _hrp_rebalance_ib_gateway,
            name="hrp_rebalance_ib_gateway",
            description=(
                "Pipeline completo para rebalanceo HRP: 1) ingesta OHLCV por ticker (`fetch_ib_gateway_ohlcv`; "
                "lake o HTTP según CAPADONNA_*/IBKR_*), 2) snapshot de pesos actuales desde `IBKR_PORTFOLIO_API_URL`, "
                "3) cálculo de pesos objetivo HRP en sandbox Strix (pypfopt con fallback scipy). "
                "Devuelve JSON con `target_weights`, `current_weights`, `weight_deltas` y `rebalance_required`."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _propose_trade_signal,
            name="propose_trade_signal",
            description=(
                "Propone una senal en finance_worker.trade_signals via StateDelta; aplica EvidenceUnique y RiskGuard. "
                "Por defecto crea PENDING_HITL en cualquier horario (lun-vie) para strategy distinto de moc_hrp_cfd; "
                "opt-in legado DUCKCLAW_QUANT_BLOCK_NON_MOC_LEDGER=1 vuelve a bloquear propuesta fuera de ventana MOC "
                "(env DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW, default 14:40:00-14:59:30 COT) con OUTSIDE_MOC_PREP_WINDOW. "
                "Con DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1, la auto-exec encadenada a execute_approved_signal solo "
                "dentro de esa ventana (paper; live exige ALLOW_LIVE); fuera, usar /execute_signal manual si aplica. "
                "moc_hrp_cfd (batch PM2): default PENDING_HITL; auto-exec encadenada solo si DUCKCLAW_MOC_BATCH_AUTO_EXECUTE=1 "
                "ademas DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1 y misma ventana MOC. "
                "Bypass dev ventana: DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES. "
                "Devuelve signal_id (UUID): `/execute_signal <signal_id>` si sigue pendiente."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _accumulate_moc_intraday_state,
            name="accumulate_moc_intraday_state",
            description=(
                "Hints intradía para MOC (sin ledger ni HITL): merge JSON en quant_core.intraday_moc_accum vía "
                "cola db-writer. Solo sesión ACTIVE, lun–vie 08:30–15:00 COT salvo barreras dev. "
                "Claves típicas: weight_scale (0–∞, clamp opcional weight_scale_max), force_hold (bool), notes (str). "
                "NO sustituye propose_trade_signal; PM2 finalize tras calc."
            ),
        )
    )
    tools.append(
        StructuredTool.from_function(
            _execute_approved_signal,
            name="execute_approved_signal",
            description=(
                "Ejecuta una senal tras HITL usando el mismo signal_id (UUID) que devolvio propose_trade_signal. "
                "Requiere human_approved o /execute_signal <signal_id> en Telegram "
                "(o encadenado desde propose si AUTO_EXECUTE+MOC window; batch moc_hrp_cfd + DUCKCLAW_MOC_BATCH_AUTO_EXECUTE). "
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
    tools.append(
        StructuredTool.from_function(
            _run_quant_signal_cycle,
            name="run_quant_signal_cycle",
            description=(
                "Flujo único para señal Quant: propone (propose_trade_signal) y opcionalmente ejecuta "
                "(execute_approved_signal) usando el signal_id real del ledger. Reduce orquestación tool-by-tool; "
                "si execute_now=false devuelve signal_id y estado PENDING_HITL, si true intenta ejecución inmediata."
            ),
        )
    )
