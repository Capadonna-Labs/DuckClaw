#!/usr/bin/env python3
"""
HRP semanal Core-Satellite — specs/features/Core-Satellite HRP Weekly + MOC CFD.md

PM2 ej.: TZ=America/Bogota, cron dominical ``0 20 * * 0``.
Requiere: REDIS_URL, DUCKCLAW_QUANT_SCRIPT_DB, HRP_CORE_SATELLITE_UNIVERSE, capacidad sandbox Docker.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "packages" / "agents" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "agents" / "src"))
if str(_REPO / "packages" / "shared" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "shared" / "src"))
if str(_REPO / "packages" / "core" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "core" / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env")
except ImportError:
    pass


def _sandbox_hrp_weekly(price_series: dict[str, list[float]]) -> str:
    payload_lit = repr(json.dumps(price_series, ensure_ascii=False))
    return f'''
import json
import pandas as pd
import numpy as np

PRICES = json.loads({payload_lit})
prices_df = pd.DataFrame(PRICES).apply(pd.to_numeric, errors="coerce").dropna(how="any")
if prices_df.shape[0] < 61 or prices_df.shape[1] < 2:
    print(json.dumps({{"ok": False, "error": "Filas/col insuf Ledoit/HRP"}}), ensure_ascii=False))
    raise SystemExit(0)
returns_df = prices_df.pct_change().dropna(how="any")
if returns_df.shape[0] < 30:
    print(json.dumps({{"ok": False, "error": "Retornos insuficientes"}}), ensure_ascii=False))
    raise SystemExit(0)
try:
    from pypfopt import HRPOpt, risk_models
    S = risk_models.CovarianceShrinkage(returns_df).ledoit_wolf()
    hrp = HRPOpt(returns=returns_df, cov_matrix=S)
    raw = hrp.optimize()
    if hasattr(raw, "to_dict"):
        raw = raw.to_dict()
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e)[:800]}}), ensure_ascii=False))
    raise SystemExit(0)
cap = 0.40
weights = {{str(k): min(float(raw[k]), cap) for k in raw.keys()}}
tot = float(sum(weights.values()))
if tot <= 1e-18:
    n = len(weights)
    weights = {{k: 1.0 / max(n, 1) for k in weights}}
else:
    weights = {{k: v / tot for k, v in weights.items()}}
print(json.dumps({{
    "ok": True,
    "weights_raw": raw,
    "weights_capped": weights,
    "n_observations": int(returns_df.shape[0]),
}}), ensure_ascii=False))
'''.strip()


def _closes_from_vault(db: Any, ticker: str, limit_rows: int = 200) -> list[float]:
    esc = ticker.replace("'", "''")
    raw = db.query(
        "SELECT close FROM quant_core.ohlcv_data "
        f"WHERE ticker = '{esc}' ORDER BY timestamp DESC LIMIT {int(limit_rows)}"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    closes = []
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        try:
            c = float(row.get("close") or 0)
        except (TypeError, ValueError):
            continue
        if c > 0:
            closes.append(c)
    return closes


def main() -> int:
    from duckclaw import DuckClaw
    from duckclaw.forge.skills.quant_market_bridge import _fetch_ib_gateway_ohlcv_impl
    from duckclaw.forge.skills.quant_tool_context import (
        bind_quant_market_evidence_chat,
        note_quant_market_evidence_ticker,
    )
    from duckclaw.graphs.sandbox import run_in_sandbox

    from scripts.quant._job_common import (
        enqueue_task_audit_warning,
        enqueue_vault_sql,
        infer_vault_user_id,
        send_quant_alert_message,
    )

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        print("[hrp_weekly] DUCKCLAW_QUANT_SCRIPT_DB inválido o archivo inexistente", file=sys.stderr)
        return 2
    raw_univ = os.environ.get("HRP_CORE_SATELLITE_UNIVERSE", "").strip()
    tickers = [t.strip().upper() for t in raw_univ.replace(";", ",").split(",") if t.strip()]
    if len(tickers) < 2:
        print("[hrp_weekly] Define HRP_CORE_SATELLITE_UNIVERSE con ≥2 tickers CSV", file=sys.stderr)
        return 2

    vault_path = str(Path(db_path).expanduser().resolve())
    uid_infer = infer_vault_user_id(vault_path)

    bind_quant_market_evidence_chat("__hrp_weekly__")
    db = DuckClaw(vault_path, read_only=True)
    LOOKBACK = 120
    MIN_ROWS = 60

    ingest_ok: dict[str, bool] = {}
    for tk in tickers:
        raw = _fetch_ib_gateway_ohlcv_impl(db, ticker=tk, timeframe="1d", lookback_days=LOOKBACK)
        parsed: dict[str, object] = {}
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else {}
        except json.JSONDecodeError:
            parsed = {}
        ingest_ok[tk] = isinstance(parsed, dict) and parsed.get("status") == "ok"
        if ingest_ok[tk]:
            note_quant_market_evidence_ticker(tk)

    bar_counts: dict[str, int] = {}
    for tk in tickers:
        cnt_raw = db.query(
            "SELECT CAST(COUNT(*) AS BIGINT) AS c FROM quant_core.ohlcv_data "
            + f"WHERE ticker = '{tk.replace(chr(39), chr(39)+chr(39))}'"
        )
        cr = json.loads(cnt_raw) if isinstance(cnt_raw, str) else (cnt_raw or [])
        c = int((cr[0] or {}).get("c") or 0) if cr and isinstance(cr[0], dict) else 0
        bar_counts[tk] = c

    short = [tk for tk, n in bar_counts.items() if n < MIN_ROWS]
    if short:
        msg_warn = "[hrp_weekly] Abort: barras<m60 " + ",".join(short)
        print(msg_warn, file=sys.stderr)
        enqueue_task_audit_warning(
            vault_path,
            tenant_id="default",
            worker_id="hrp_weekly_job",
            plan_title="HRP_WEEKLY_INSUFFICIENT_BARS",
            query_prefix=msg_warn[:220],
        )
        send_quant_alert_message(f"⚠️ HRP semanal abortado · barras &lt; {MIN_ROWS}: {short}")
        return 1

    series: dict[str, list[float]] = {}
    for tk in tickers:
        closes = _closes_from_vault(db, tk, limit_rows=200)
        if len(closes) >= MIN_ROWS:
            series[tk] = closes[-LOOKBACK:]

    if len(series) < 2:
        print("[hrp_weekly] Series insuficientes tras ingest", file=sys.stderr)
        return 1

    sandbox_code = _sandbox_hrp_weekly(series)
    res = run_in_sandbox(
        db=db,
        llm=None,
        code=sandbox_code,
        language="python",
        original_request="hrp_weekly_job core-satellite",
        max_retries=1,
        worker_id="Quant-Trader",
    )
    parsed_out: dict[str, object] | None = None
    for line in reversed((res.stdout or "").splitlines()):
        ln = line.strip()
        if not ln.startswith("{"):
            continue
        try:
            parsed_out = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_out, dict):
            break
        parsed_out = None
    if parsed_out is None or not parsed_out.get("ok"):
        err = parsed_out.get("error") if isinstance(parsed_out, dict) else "sandbox"
        print(f"[hrp_weekly] sandbox falló: {err}", file=sys.stderr)
        return 1

    weights_capped = parsed_out.get("weights_capped")
    weights_raw = parsed_out.get("weights_raw") or weights_capped
    n_obs = int(parsed_out.get("n_observations") or 0)
    if not isinstance(weights_capped, dict):
        print("[hrp_weekly] sin weights_capped", file=sys.stderr)
        return 1

    ticker_max = ""
    ticker_min = ""
    wmax = -1.0
    wmin = 1e9
    capped_vals: dict[str, float] = {}
    for tk, wv in weights_capped.items():
        try:
            wf = float(wv)
        except (TypeError, ValueError):
            continue
        capped_vals[str(tk).upper()] = wf
        if wf > wmax:
            wmax = wf
            ticker_max = str(tk).upper()
        if wf < wmin:
            wmin = wf
            ticker_min = str(tk).upper()
    if not capped_vals:
        print("[hrp_weekly] weights_capped vacío", file=sys.stderr)
        return 1

    wt_keys = list(weights_capped.keys())
    placeholders = ",".join(["?"] * len(wt_keys))
    purge_ok, purge_err = enqueue_vault_sql(
        db_path=vault_path,
        sql=(
            "DELETE FROM quant_core.hrp_mandates hm "
            "WHERE date_trunc('day', hm.computed_at) = date_trunc('day', CURRENT_TIMESTAMP) "
            f"AND hm.ticker IN ({placeholders})"
        ),
        params=[str(k).upper()[:20] for k in wt_keys],
        tenant_id="default",
        user_id_override=uid_infer,
    )
    if not purge_ok:
        print("[hrp_weekly] purge aviso:", purge_err, file=sys.stderr)

    shrink = "ledoit_wolf"
    tenant = "default"
    for tk, wc in weights_capped.items():
        wr = weights_raw.get(tk, wc) if isinstance(weights_raw, dict) else wc
        try:
            wc_f = float(wc)
            wr_f = float(wr)
        except (TypeError, ValueError):
            continue
        ok_ins, ierr = enqueue_vault_sql(
            db_path=vault_path,
            sql=(
                "INSERT INTO quant_core.hrp_mandates "
                "(ticker, hrp_weight, hrp_weight_capped, lookback_days, n_observations, computed_at, valid_until, shrinkage_method) "
                "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '7 days', ?)"
            ),
            params=[str(tk).upper()[:20], wr_f, wc_f, LOOKBACK, int(n_obs), shrink],
            tenant_id=tenant,
            user_id_override=uid_infer,
        )
        if not ok_ins:
            print(f"[hrp_weekly] insert {tk}: {ierr}", file=sys.stderr)

    bogota_note = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    telegram_body = (
        f"⚖️ HRP Semanal actualizado — {bogota_note}\n"
        f"Tickers: {len(weights_capped)} · Lookback: {LOOKBACK}d · Shrinkage: Ledoit-Wolf\n"
        f"Mayor peso: {ticker_max or '—'} ({(wmax * 100) if wmax >= 0 else 0:.1f}%)\n"
        f"Menor peso: {ticker_min or '—'} ({(wmin * 100):.1f}%)"
    )
    send_quant_alert_message(telegram_body.replace("<", "&lt;"))
    print(json.dumps({"ok": True, "tickers_written": len(weights_capped)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
