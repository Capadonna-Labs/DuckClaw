#!/usr/bin/env python3
"""
Crea una señal Quant Trader mínima en ``finance_worker.trade_signals`` (con ``human_approved``)
y ejecuta el mismo camino que la tool ``execute_approved_signal``.

Uso típico (paper; sin ``IBKR_EXECUTE_ORDER_URL`` la ejecución es **simulada**):

  uv run python scripts/capadonna/create_and_execute_quant_signal.py --db /ruta/a/vault.duckdb

Carga ``.env`` del repo (``python-dotenv``) para ``IBKR_EXECUTE_ORDER_URL`` / Bearer.
Fuerza ``IBKR_ACCOUNT_MODE=paper`` en este proceso (coherente con sesión por defecto; tu ``.env`` puede tener ``live`` para el gateway).

No edita el plan adjunto; es utilidad de desarrollo/operación.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "core" / "src"))
    sys.path.insert(0, str(_REPO / "packages" / "agents" / "src"))

from duckclaw import DuckClaw  # noqa: E402
from duckclaw.forge.skills.quant_tool_context import set_quant_tool_db_path  # noqa: E402
from duckclaw.forge.skills.quant_trader_bridge import _execute_approved_signal_impl  # noqa: E402

# Misma DDL base que ``services/db-writer/quant_state_delta_handler.py`` (fragmento ledger).
_LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS finance_worker;
CREATE SCHEMA IF NOT EXISTS quant_core;

CREATE TABLE IF NOT EXISTS finance_worker.trading_mandates (
  mandate_id UUID PRIMARY KEY,
  source_worker VARCHAR,
  asset_class VARCHAR,
  direction VARCHAR,
  max_weight_pct DECIMAL(5,2),
  status VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.trade_signals (
  signal_id UUID PRIMARY KEY,
  mandate_id UUID REFERENCES finance_worker.trading_mandates(mandate_id),
  ticker VARCHAR,
  signal_type VARCHAR,
  proposed_weight DECIMAL(5,2),
  sandbox_backtest_cid VARCHAR,
  human_approved BOOLEAN DEFAULT FALSE,
  status VARCHAR,
  rationale VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
  id VARCHAR PRIMARY KEY,
  mode VARCHAR NOT NULL,
  tickers VARCHAR NOT NULL DEFAULT '',
  session_uid VARCHAR,
  session_goal JSON,
  status VARCHAR NOT NULL DEFAULT 'ACTIVE',
  anchor_equity DOUBLE,
  peak_equity DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_schema(db: DuckClaw) -> None:
    for chunk in _LEDGER_DDL.split(";"):
        stmt = chunk.strip()
        if stmt:
            db.execute(stmt)


def main() -> int:
    p = argparse.ArgumentParser(description="Inserta señal Quant y ejecuta execute_approved_signal.")
    p.add_argument(
        "--db",
        default=os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB", "").strip(),
        help="Ruta al .duckdb (o :memory:). Si vacío, usa env DUCKCLAW_QUANT_SCRIPT_DB.",
    )
    p.add_argument("--ticker", default="SPY", help="Símbolo (default SPY).")
    p.add_argument("--weight", type=float, default=1.0, help="proposed_weight %% (default 1).")
    p.add_argument(
        "--signal-type",
        default="ENTRY",
        choices=("ENTRY", "EXIT"),
        dest="signal_type",
    )
    p.add_argument(
        "--insert-only",
        action="store_true",
        help="Solo INSERT; no llama al broker (imprime signal_id).",
    )
    args = p.parse_args()
    db_path = (args.db or "").strip()
    if not db_path:
        print("Indica --db /ruta/vault.duckdb o export DUCKCLAW_QUANT_SCRIPT_DB=", file=sys.stderr)
        return 2

    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env")
    except ImportError:
        pass
    # Sesión DuckDB por defecto es paper; sin esto, .env con IBKR_ACCOUNT_MODE=live choca con execute_approved_signal.
    os.environ["IBKR_ACCOUNT_MODE"] = "paper"

    mandate_id = uuid.uuid4()
    signal_id = uuid.uuid4()
    sid_str = str(signal_id)

    abs_path = str(Path(db_path).expanduser().resolve()) if db_path != ":memory:" else ":memory:"
    set_quant_tool_db_path(abs_path)

    # engine=python: INSERT parametrizado estable; una sola conexión para :memory:.
    db = DuckClaw(abs_path, read_only=False, engine="python")
    try:
        _ensure_schema(db)
        db.execute(
            """
            INSERT INTO finance_worker.trading_mandates
            (mandate_id, source_worker, asset_class, direction, max_weight_pct, status)
            VALUES (?, 'script', 'EQUITY', 'LONG', 25.0, 'ACTIVE')
            """,
            [str(mandate_id)],
        )
        db.execute(
            """
            INSERT INTO finance_worker.trade_signals
            (signal_id, mandate_id, ticker, signal_type, proposed_weight, human_approved, status, rationale)
            VALUES (?, ?, ?, ?, ?, TRUE, 'READY', ?)
            """,
            [
                sid_str,
                str(mandate_id),
                args.ticker.strip().upper(),
                args.signal_type,
                float(args.weight),
                "create_and_execute_quant_signal.py",
            ],
        )

        print(json.dumps({"created": True, "signal_id": sid_str, "mandate_id": str(mandate_id)}, indent=2))
        if args.insert_only:
            print("insert-only: no se invoca execute_approved_signal.")
            return 0

        out = _execute_approved_signal_impl(db, signal_id=sid_str)
    finally:
        db.close()

    print(out)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return 1
    if payload.get("error"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
