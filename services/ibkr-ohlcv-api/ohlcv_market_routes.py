"""
Rutas FastAPI para GET /api/market/ohlcv y GET /api/market/ibkr/historical (contrato DuckClaw).

Montar con app.include_router en Capadonna Observability (puerto 8002) o en la app
standalone de main.py.

1) Lake: OHLCV_LAKE_PYTHON / OHLCV_LAKE_SCRIPT o defaults bajo project_root.
2) Fallback IB Gateway: si el lake no devuelve barras o falla el export, y
   OHLCV_IB_FALLBACK no es ``0``, se ejecuta scripts/capadonna/ibkr_historical_bars.py
   (o OHLCV_IB_PYTHON + OHLCV_IB_SCRIPT) si el script existe / venv tiene ib_async.
3) ``/api/market/ibkr/historical``: solo IB Gateway (sin intentar lake).
4) ``POST /api/broker/execute``: cuerpo JSON mínimo ``{"signal_id","paper"}``; opcional payload
   enriquecido (``ticker``, ``signal_type``, ``proposed_weight``, ``mandate_id`` para modo peso;
   ``action``, ``quantity`` para modo acciones) inyectado como ``DUCKCLAW_EMBEDDED_EXECUTE_JSON``
   en el hook.
   Cabecera opcional ``X-Duckclaw-IBKR-Account-Mode: paper|live`` (como el portafolio).
   Modo efectivo: ``OHLCV_BROKER_EXECUTE_FORCE_PAPER`` (1/true) fuerza paper; si no, la
   cabecera manda si es válida; si falta o es inválida, se usa ``body.paper`` (default True).
   Auth Bearer opcional (OHLCV_API_KEY / IBKR_PORTFOLIO_API_KEY). Sin hook Python/script,
   responde 501.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["market"])

_TF_SAFE = re.compile(r"^[0-9A-Za-z]+$")
_MAX_LOOKBACK = 4000


def _expected_bearer_token() -> str:
    return (os.environ.get("OHLCV_API_KEY") or os.environ.get("IBKR_PORTFOLIO_API_KEY") or "").strip()


def _auth_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "error", "message": message})


def _check_bearer(request: Request) -> JSONResponse | None:
    want = _expected_bearer_token()
    if not want:
        return None
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return _auth_error(401, "Missing or invalid Authorization header")
    got = auth[7:].strip()
    if got != want:
        return _auth_error(401, "Invalid bearer token")
    return None


class _ExecuteApprovedBody(BaseModel):
    signal_id: str = Field(..., min_length=32, max_length=64)
    paper: bool = True
    ticker: str | None = Field(default=None, max_length=32)
    signal_type: str | None = Field(default=None, max_length=16)
    proposed_weight: float | None = Field(default=None)
    mandate_id: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=8)
    quantity: float | None = Field(default=None)


def _resolve_execute_order_hook() -> tuple[str, str] | None:
    py = (os.environ.get("OHLCV_EXECUTE_ORDER_PYTHON") or "").strip()
    script = (os.environ.get("OHLCV_EXECUTE_ORDER_SCRIPT") or "").strip()
    if py and script:
        return py, script
    return None


_DUCKCLAW_IBKR_ACCOUNT_MODE_HEADER = "X-Duckclaw-IBKR-Account-Mode"


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _effective_account_mode_paper(request: Request, body: _ExecuteApprovedBody) -> bool:
    """Paper por defecto si la cabecera falta o no es paper/live."""
    if _env_truthy("OHLCV_BROKER_EXECUTE_FORCE_PAPER"):
        return True
    raw = (request.headers.get(_DUCKCLAW_IBKR_ACCOUNT_MODE_HEADER) or "").strip().lower()
    if raw == "live":
        return False
    if raw == "paper":
        return True
    return bool(body.paper)


def _embedded_execute_json(body: _ExecuteApprovedBody) -> str | None:
    """Serializa plan de ejecución para el hook (prioridad: acciones > peso)."""
    tkr_raw = (body.ticker or "").strip().upper()
    if tkr_raw:
        act = (body.action or "").strip().upper()
        if act in ("BUY", "SELL") and body.quantity is not None:
            try:
                q = float(body.quantity)
            except (TypeError, ValueError):
                q = 0.0
            if q > 0:
                return json.dumps(
                    {"mode": "shares", "ticker": tkr_raw, "action": act, "quantity": q},
                    separators=(",", ":"),
                )
        if body.proposed_weight is not None:
            try:
                w = float(body.proposed_weight)
            except (TypeError, ValueError):
                w = 0.0
            if w > 0:
                st = (body.signal_type or "ENTRY").strip().upper()
                if st not in ("ENTRY", "EXIT"):
                    st = "ENTRY"
                payload: dict[str, Any] = {
                    "mode": "weight",
                    "ticker": tkr_raw,
                    "signal_type": st,
                    "proposed_weight": w,
                }
                mid = (body.mandate_id or "").strip()
                if mid:
                    payload["mandate_id"] = mid
                return json.dumps(payload, separators=(",", ":"))
    return None


def _project_root() -> Path:
    raw = (os.environ.get("OHLCV_PROJECT_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def _resolve_lake_paths() -> tuple[str, str] | None:
    py = (os.environ.get("OHLCV_LAKE_PYTHON") or "").strip()
    script = (os.environ.get("OHLCV_LAKE_SCRIPT") or "").strip()
    if py and script:
        return py, script
    root = _project_root()
    py2 = root / ".venv" / "bin" / "python"
    sc2 = root / "scripts" / "export_lake_ohlcv.py"
    if py2.is_file() and sc2.is_file():
        return str(py2), str(sc2)
    return None


def _resolve_ib_paths() -> tuple[str, str] | None:
    if (os.environ.get("OHLCV_IB_FALLBACK") or "").strip() == "0":
        return None
    py = (os.environ.get("OHLCV_IB_PYTHON") or "").strip()
    script = (os.environ.get("OHLCV_IB_SCRIPT") or "").strip()
    if py and script:
        return py, script
    root = _project_root()
    sc2 = root / "scripts" / "capadonna" / "ibkr_historical_bars.py"
    if not sc2.is_file():
        return None
    lake = _resolve_lake_paths()
    if lake:
        return lake[0], str(sc2)
    py2 = root / ".venv" / "bin" / "python"
    if py2.is_file():
        return str(py2), str(sc2)
    return None


def _lake_export_argv(ticker: str, timeframe: str, lookback_days: int) -> list[str] | JSONResponse:
    resolved = _resolve_lake_paths()
    if not resolved:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": (
                    "Lake export not configured: set OHLCV_LAKE_PYTHON and OHLCV_LAKE_SCRIPT, "
                    "or install export_lake_ohlcv.py under scripts/ with project .venv."
                ),
            },
        )
    py, script = resolved
    return [py, script, ticker.upper(), timeframe, str(lookback_days)]


def _timeout_seconds(env_name: str, default: str = "120") -> int:
    raw = (os.environ.get(env_name) or default).strip() or default
    try:
        timeout = int(raw)
    except ValueError:
        timeout = int(default)
    return max(10, min(timeout, 600))


def _run_lake_export(ticker: str, timeframe: str, lookback_days: int) -> dict[str, Any] | JSONResponse:
    argv = _lake_export_argv(ticker, timeframe, lookback_days)
    if isinstance(argv, JSONResponse):
        return argv
    timeout = _timeout_seconds("OHLCV_LAKE_EXPORT_TIMEOUT", "120")
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "Lake export timed out"},
        )
    except OSError as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to spawn lake export: {e!s}"},
        )
    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "")[-500:]
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Lake export exited {proc.returncode}: {err_tail}",
            },
        )
    raw = (proc.stdout or "").strip()
    if not raw:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Lake export produced empty stdout"},
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Lake export returned invalid JSON: {e}"},
        )


def _run_ib_export(ticker: str, timeframe: str, lookback_days: int) -> dict[str, Any] | JSONResponse:
    resolved = _resolve_ib_paths()
    if not resolved:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "IB historical fallback not configured (missing script or OHLCV_IB_FALLBACK=0)"},
        )
    py, script = resolved
    argv = [py, script, ticker.upper(), timeframe, str(lookback_days)]
    timeout = _timeout_seconds("OHLCV_IB_EXPORT_TIMEOUT", "90")
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "IB historical export timed out"},
        )
    except OSError as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Failed to spawn IB export: {e!s}"},
        )
    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "")[-500:]
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": f"IB historical exited {proc.returncode}: {err_tail}",
            },
        )
    raw = (proc.stdout or "").strip()
    if not raw:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "IB historical produced empty stdout"},
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": f"IB historical returned invalid JSON: {e}"},
        )


def _bars_from_export_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    bars = payload.get("bars")
    if not isinstance(bars, list):
        return []
    return [b for b in bars if isinstance(b, dict)]


def _to_iso_z(bar_ts: Any) -> str:
    s = str(bar_ts or "").strip()
    if not s:
        return ""
    if "T" in s:
        return s if s.endswith("Z") else f"{s}Z"
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return s


def _contract_bar(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        ts = _to_iso_z(row.get("timestamp") or row.get("time") or row.get("date"))
        if not ts:
            return None
        return {
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0) or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _payload_to_contract_data(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_bars = _bars_from_export_payload(payload)
    data: list[dict[str, Any]] = []
    for b in raw_bars:
        c = _contract_bar(b)
        if c:
            data.append(c)
    return data


def _validated_ohlcv_query(
    ticker: str, timeframe: str, lookback_days: Any
) -> JSONResponse | tuple[str, str, int]:
    """Valida ticker/timeframe/lookback; devuelve JSONResponse 400 o (tkr, tf, lb)."""
    tkr = (ticker or "").strip().upper()
    if not tkr or len(tkr) > 12 or not re.fullmatch(r"[0-9A-Z.\-]+", tkr):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid ticker"},
        )

    tf = (timeframe or "").strip()
    if not tf or len(tf) > 16 or not _TF_SAFE.fullmatch(tf):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid timeframe"},
        )

    try:
        lb = max(1, min(int(lookback_days), _MAX_LOOKBACK))
    except (TypeError, ValueError):
        lb = 7
    return (tkr, tf, lb)


@router.get("/api/market/ibkr/historical", response_model=None)
def market_ibkr_historical(
    request: Request,
    ticker: str,
    timeframe: str,
    lookback_days: int = 7,
) -> dict[str, Any] | JSONResponse:
    """Solo IB Gateway vía ibkr_historical_bars.py; no consulta el lake."""
    bad = _check_bearer(request)
    if bad is not None:
        return bad

    validated = _validated_ohlcv_query(ticker, timeframe, lookback_days)
    if isinstance(validated, JSONResponse):
        return validated
    tkr, tf, lb = validated

    if _resolve_ib_paths() is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "IB historical not configured (missing script or OHLCV_IB_FALLBACK=0)",
            },
        )

    ib_res = _run_ib_export(tkr, tf, lb)
    if isinstance(ib_res, JSONResponse):
        return ib_res
    if isinstance(ib_res, dict):
        data_ib = _payload_to_contract_data(ib_res)
        if data_ib:
            return {
                "status": "success",
                "ticker": tkr,
                "timeframe": tf,
                "data": data_ib,
            }
        ib_msg = ib_res.get("message") if isinstance(ib_res.get("message"), str) else None
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": ib_msg or f"No OHLCV bars from IB Gateway for {tkr} timeframe={tf} lookback_days={lb}",
            },
        )
    return ib_res


@router.get("/api/market/ohlcv", response_model=None)
def market_ohlcv(
    request: Request,
    ticker: str,
    timeframe: str,
    lookback_days: int = 7,
) -> dict[str, Any] | JSONResponse:
    """Contrato DuckClaw: lake primero; si no hay velas (o lake falla), fallback IB Gateway."""
    bad = _check_bearer(request)
    if bad is not None:
        return bad

    validated = _validated_ohlcv_query(ticker, timeframe, lookback_days)
    if isinstance(validated, JSONResponse):
        return validated
    tkr, tf, lb = validated

    lake_err: JSONResponse | None = None
    lake_payload: dict[str, Any] | None = None

    lake_result = _run_lake_export(tkr, tf, lb)
    if isinstance(lake_result, JSONResponse):
        lake_err = lake_result
    elif isinstance(lake_result, dict):
        lake_payload = lake_result

    data = _payload_to_contract_data(lake_payload) if lake_payload else []
    if data:
        return {"status": "success", "ticker": tkr, "timeframe": tf, "data": data}

    ib_allowed = _resolve_ib_paths() is not None
    if ib_allowed:
        ib_res = _run_ib_export(tkr, tf, lb)
        if isinstance(ib_res, dict):
            data_ib = _payload_to_contract_data(ib_res)
            if data_ib:
                return {
                    "status": "success",
                    "ticker": tkr,
                    "timeframe": tf,
                    "data": data_ib,
                }
            ib_msg = ib_res.get("message") if isinstance(ib_res.get("message"), str) else None
            if lake_err is not None:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": (
                            f"Lake failed or empty; IB fallback returned no bars. "
                            f"IB hint: {ib_msg or 'no bars'}"
                        ),
                    },
                )
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": ib_msg or f"No OHLCV bars from lake or IB for {tkr} timeframe={tf} lookback_days={lb}",
                },
            )
        if lake_err is not None:
            return lake_err
        return ib_res

    hint = None
    if lake_payload and isinstance(lake_payload.get("message"), str):
        hint = lake_payload["message"]
    if lake_err is not None:
        return lake_err
    msg = hint or f"No OHLCV bars in lake for {tkr} timeframe={tf} lookback_days={lb}"
    return JSONResponse(status_code=400, content={"status": "error", "message": msg})


@router.post("/api/broker/execute", response_model=None)
def post_broker_execute(request: Request, body: _ExecuteApprovedBody) -> JSONResponse | dict[str, Any]:
    """POST alineado con ``execute_order`` / ``execute_approved_signal`` en Duckclaw."""
    err = _check_bearer(request)
    if err is not None:
        return err
    hook = _resolve_execute_order_hook()
    if hook is None:
        return JSONResponse(
            status_code=501,
            content={
                "status": "error",
                "message": (
                    "Order execution hook not configured. Set OHLCV_EXECUTE_ORDER_PYTHON and "
                    "OHLCV_EXECUTE_ORDER_SCRIPT on this host, or point IBKR_EXECUTE_ORDER_URL elsewhere."
                ),
            },
        )
    py, script = hook
    sid = body.signal_id.strip().lower()
    effective_paper = _effective_account_mode_paper(request, body)
    paper_flag = "1" if effective_paper else "0"
    raw_timeout = (os.environ.get("OHLCV_EXECUTE_ORDER_TIMEOUT") or "120").strip() or "120"
    try:
        timeout_sec = max(1, min(600, int(raw_timeout)))
    except ValueError:
        timeout_sec = 120
    child_env = os.environ.copy()
    emb = _embedded_execute_json(body)
    if emb:
        child_env["DUCKCLAW_EMBEDDED_EXECUTE_JSON"] = emb
    try:
        proc = subprocess.run(
            [py, script, sid, paper_flag],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "execute_order hook timed out"},
        )
    except OSError as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"execute_order hook failed to start: {exc}"},
        )
    out = (proc.stdout or "").strip()
    err_txt = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = err_txt
        if not msg and out.startswith("{"):
            try:
                parsed_err = json.loads(out)
                if isinstance(parsed_err, dict):
                    inner = parsed_err.get("message")
                    if isinstance(inner, str) and inner.strip():
                        msg = inner.strip()[:8000]
            except json.JSONDecodeError:
                pass
        if not msg:
            msg = f"execute_order hook exited with code {proc.returncode}"
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": msg,
            },
        )
    if out.startswith("{"):
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            merged: dict[str, Any] = {"status": "success"}
            merged.update(parsed)
            return merged
    return {"status": "success", "message": out[:8000] if out else "(empty stdout)"}
