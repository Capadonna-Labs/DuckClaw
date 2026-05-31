#!/usr/bin/env python3
"""
Imprime JSON de snapshot de cuenta/posiciones IB Gateway (ib_async) en stdout.

Contrato DuckClaw (get_ibkr_portfolio):
  total_value | net_liquidation, portfolio[] con symbol, quantity, market_value, unrealized_pnl

Entorno:
  IB_HOST=127.0.0.1  IB_PORT=4002|4001  IB_ENV=paper|live
  IBKR_SNAPSHOT_CLIENT_ID o PORTFOLIO_IB_CLIENT_ID (default 999; distinto de OHLCV_IB_CLIENT_ID)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

_DU_PAPER = re.compile(r"^DU\d+$", re.IGNORECASE)


def _emit(payload: dict[str, Any], *, rc: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(rc)


def _ib_port() -> int:
    raw = (os.environ.get("IB_PORT") or "").strip()
    if raw:
        try:
            p = int(raw)
            if p > 0:
                return p
        except ValueError:
            pass
    ib_env = (os.environ.get("IB_ENV") or os.environ.get("TWS_ENV") or "paper").lower()
    return 4002 if ib_env == "paper" else 4001


def _client_id() -> int:
    raw = (
        os.environ.get("IBKR_SNAPSHOT_CLIENT_ID")
        or os.environ.get("PORTFOLIO_IB_CLIENT_ID")
        or os.environ.get("IB_CLIENT_ID")
        or "999"
    ).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 999


def _paper_from_account(account_id: str) -> bool | None:
    aid = (account_id or "").strip()
    if _DU_PAPER.match(aid):
        return True
    if aid and not aid.upper().startswith("DU"):
        return False
    ib_env = (os.environ.get("IB_ENV") or "paper").lower()
    return ib_env == "paper"


def main() -> None:
    try:
        from ib_async import IB
    except ImportError:
        _emit(
            {"error": "snapshot_unavailable", "message": "ib_async not installed"},
            rc=1,
        )

    host = (os.environ.get("IB_HOST") or "127.0.0.1").strip()
    port = _ib_port()
    client_id = _client_id()

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=45)
    except Exception as exc:
        _emit(
            {
                "error": "snapshot_unavailable",
                "message": f"IB connect failed: {exc!s}",
            },
            rc=1,
        )

    account = ""
    try:
        accounts = list(ib.managedAccounts() or [])
        account = accounts[0] if accounts else ""
        if not account:
            _emit(
                {
                    "error": "snapshot_unavailable",
                    "message": "No managed accounts from IB Gateway",
                },
                rc=1,
            )

        ib.reqAccountSummary()
        time.sleep(1.5)

        net_liq: float | None = None
        cash: float | None = None
        for av in ib.accountSummary():
            tag = str(getattr(av, "tag", "") or "")
            cur = str(getattr(av, "currency", "") or "")
            acct = str(getattr(av, "account", "") or "")
            if acct and acct != account:
                continue
            if cur not in ("USD", "BASE", ""):
                continue
            try:
                val = float(av.value)
            except (TypeError, ValueError):
                continue
            if tag == "NetLiquidation" and net_liq is None:
                net_liq = val
            elif tag in ("TotalCashValue", "CashBalance") and cash is None:
                cash = val

        portfolio: list[dict[str, Any]] = []
        for pos in ib.positions():
            acct = str(getattr(pos, "account", "") or "")
            if acct and acct != account:
                continue
            contract = getattr(pos, "contract", None)
            sym = str(getattr(contract, "symbol", "") or "").strip().upper()
            if not sym:
                continue
            try:
                qty = float(getattr(pos, "position", 0) or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty == 0:
                continue
            row: dict[str, Any] = {
                "symbol": sym,
                "quantity": qty,
                "position": qty,
            }
            try:
                avg = float(getattr(pos, "avgCost", 0) or 0)
                if avg:
                    row["average_cost"] = avg
                    row["market_value"] = abs(qty) * avg
            except (TypeError, ValueError):
                pass
            portfolio.append(row)

        total = net_liq if net_liq is not None else 0.0
        if total == 0 and portfolio:
            total = sum(float(p.get("market_value") or 0) for p in portfolio)

        paper = _paper_from_account(account)
        payload: dict[str, Any] = {
            "status": "success",
            "account_id": account,
            "total_value": total,
            "net_liquidation": net_liq if net_liq is not None else total,
            "portfolio": portfolio,
            "positions": portfolio,
            "count": len(portfolio),
        }
        if cash is not None:
            payload["cash"] = cash
            payload["cash_balance"] = cash
        if paper is not None:
            payload["paper"] = paper
            payload["account_mode"] = "paper" if paper else "live"
        _emit(payload, rc=0)
    finally:
        try:
            ib.cancelAccountSummary()
        except Exception:
            pass
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
