"""
GET /api/portfolio/summary y GET /api/positions (contrato DuckClaw get_ibkr_portfolio).

Ejecuta scripts/capadonna/ibkr_portfolio_snapshot.py vía subprocess.
Modo cuenta: cabecera X-Duckclaw-IBKR-Account-Mode (paper|live) → IB_PORT 4002|4001.
Reintento modo opuesto si snapshot_unavailable (IBKR_ACCOUNT_MODE_ALT_FALLBACK, default on).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ohlcv_market_routes import (
    _DUCKCLAW_IBKR_ACCOUNT_MODE_HEADER,
    _check_bearer,
    _env_truthy,
    _project_root,
)

router = APIRouter(tags=["portfolio"])


def _resolve_portfolio_hook() -> tuple[str, str] | None:
    py = (os.environ.get("OHLCV_PORTFOLIO_PYTHON") or os.environ.get("OHLCV_IB_PYTHON") or "").strip()
    script = (os.environ.get("OHLCV_PORTFOLIO_SCRIPT") or "").strip()
    if py and script:
        return py, script
    root = _project_root()
    sc = root / "scripts" / "capadonna" / "ibkr_portfolio_snapshot.py"
    py2 = root / ".venv" / "bin" / "python"
    if sc.is_file() and py2.is_file():
        return str(py2), str(sc)
    return None


def _mode_from_request(request: Request) -> str:
    raw = (request.headers.get(_DUCKCLAW_IBKR_ACCOUNT_MODE_HEADER) or "").strip().lower()
    if raw == "live":
        return "live"
    if raw == "paper":
        return "paper"
    default = (os.environ.get("IB_ENV") or os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    return "live" if default == "live" else "paper"


def _port_for_mode(mode: str) -> int:
    if mode == "live":
        raw = (os.environ.get("IB_PORT_LIVE") or "").strip()
        if raw:
            try:
                p = int(raw)
                if p > 0:
                    return p
            except ValueError:
                pass
        return 4001
    raw = (os.environ.get("IB_PORT_PAPER") or os.environ.get("IB_PORT") or "").strip()
    if raw:
        try:
            p = int(raw)
            if p > 0:
                return p
        except ValueError:
            pass
    return 4002


def _snapshot_has_substance(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    err = str(data.get("error") or data.get("message") or "").lower()
    if "snapshot_unavailable" in err:
        return False
    portfolio = data.get("portfolio") or data.get("positions") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []
    if portfolio:
        return True
    for key in ("total_value", "net_liquidation", "cash", "cash_balance"):
        v = data.get(key)
        if v is None:
            continue
        try:
            if float(v) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _run_snapshot(mode: str) -> dict[str, Any] | JSONResponse:
    hook = _resolve_portfolio_hook()
    if hook is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Portfolio snapshot not configured (missing ibkr_portfolio_snapshot.py)",
            },
        )
    py, script = hook
    raw_timeout = (os.environ.get("OHLCV_PORTFOLIO_TIMEOUT") or "60").strip() or "60"
    try:
        timeout_sec = max(5, min(180, int(raw_timeout)))
    except ValueError:
        timeout_sec = 60

    child_env = os.environ.copy()
    child_env["IB_ENV"] = mode
    child_env["IB_PORT"] = str(_port_for_mode(mode))

    try:
        proc = subprocess.run(
            [py, script],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"error": "snapshot_unavailable", "message": "portfolio snapshot timed out"},
        )
    except OSError as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_unavailable", "message": f"portfolio hook failed: {exc}"},
        )

    out = (proc.stdout or "").strip()
    err_txt = (proc.stderr or "").strip()
    if not out.startswith("{"):
        msg = err_txt or out or f"portfolio hook exited with code {proc.returncode}"
        return JSONResponse(
            status_code=502,
            content={"error": "snapshot_unavailable", "message": msg[:8000]},
        )
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=502,
            content={"error": "snapshot_unavailable", "message": "invalid JSON from portfolio hook"},
        )
    if not isinstance(parsed, dict):
        return JSONResponse(
            status_code=502,
            content={"error": "snapshot_unavailable", "message": "portfolio hook returned non-object JSON"},
        )
    if proc.returncode != 0 and not parsed.get("error"):
        parsed = dict(parsed)
        parsed["error"] = "snapshot_unavailable"
        if err_txt and not parsed.get("message"):
            parsed["message"] = err_txt[:8000]
    return parsed


def _resolve_snapshot(request: Request) -> dict[str, Any] | JSONResponse:
    configured = _mode_from_request(request)
    data = _run_snapshot(configured)
    if isinstance(data, JSONResponse):
        return data
    if _env_truthy("IBKR_ACCOUNT_MODE_ALT_FALLBACK") or (
        os.environ.get("IBKR_ACCOUNT_MODE_ALT_FALLBACK") or "1"
    ).strip().lower() not in ("0", "false", "no"):
        err = str(data.get("error") or data.get("message") or "").lower()
        if "snapshot_unavailable" in err or not _snapshot_has_substance(data):
            alt = "live" if configured == "paper" else "paper"
            if alt != configured:
                alt_data = _run_snapshot(alt)
                if isinstance(alt_data, dict) and _snapshot_has_substance(alt_data):
                    alt_data = dict(alt_data)
                    alt_data["effective_mode"] = alt
                    alt_data["configured_mode"] = configured
                    return alt_data
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault("effective_mode", configured)
        data.setdefault("configured_mode", configured)
    return data


@router.get("/api/portfolio/summary", response_model=None)
def portfolio_summary(request: Request) -> dict[str, Any] | JSONResponse:
    bad = _check_bearer(request)
    if bad is not None:
        return bad
    return _resolve_snapshot(request)


@router.get("/api/positions", response_model=None)
def portfolio_positions(request: Request) -> dict[str, Any] | JSONResponse:
    bad = _check_bearer(request)
    if bad is not None:
        return bad
    data = _resolve_snapshot(request)
    if isinstance(data, JSONResponse):
        return data
    positions = data.get("positions") or data.get("portfolio") or []
    if isinstance(positions, dict):
        positions = list(positions.values()) if positions else []
    return {
        "status": data.get("status", "success"),
        "positions": positions,
        "portfolio": positions,
        "total_value": data.get("total_value") or data.get("net_liquidation"),
        "net_liquidation": data.get("net_liquidation") or data.get("total_value"),
        "count": len(positions) if isinstance(positions, list) else data.get("count"),
        "account_id": data.get("account_id"),
        "paper": data.get("paper"),
        "effective_mode": data.get("effective_mode"),
    }
