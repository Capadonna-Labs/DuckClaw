#!/usr/bin/env python3
"""Place protective GTC TP/SL (OCA) for existing IBKR positions with ACTIVE levels.

Does NOT send a new market entry — only closing Limit (TP) + Stop (SL).

Usage:
  uv run python scripts/place_protective_gtc_brackets.py --dry-run
  uv run python scripts/place_protective_gtc_brackets.py --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def _run(*, vault: str, dry_run: bool, tickers: list[str] | None) -> int:
    import duckdb

    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_protective_oca_orders
    from duckclaw.write_commands import InsertIbkrOrderCommand

    con = duckdb.connect(vault, read_only=True)
    levels = con.execute(
        """
        SELECT ticker, take_profit, stop_loss
        FROM quant_core.tp_sl_levels
        WHERE upper(cast(status AS VARCHAR)) = 'ACTIVE'
        ORDER BY ticker
        """
    ).fetchall()
    positions = {
        str(r[0]).upper(): float(r[1])
        for r in con.execute(
            "SELECT ticker, qty FROM quant_core.portfolio_positions WHERE qty != 0"
        ).fetchall()
    }
    con.close()

    plan: list[dict] = []
    for ticker, tp, sl in levels:
        t = str(ticker).upper()
        if tickers and t not in tickers:
            continue
        qty = positions.get(t)
        if qty is None:
            print(f"SKIP {t}: ACTIVE tp/sl but no portfolio_positions row")
            continue
        if abs(qty) < 1e-9:
            print(f"SKIP {t}: zero qty")
            continue
        side = "BUY" if qty > 0 else "SELL"
        plan.append(
            {
                "ticker": t,
                "side": side,
                "quantity": int(abs(qty)),
                "tp_price": float(tp) if tp is not None else None,
                "sl_price": float(sl) if sl is not None else None,
            }
        )

    if not plan:
        print("Nothing to place.")
        return 1

    print("Plan (protective GTC OCA — no new entry):")
    for p in plan:
        print(
            f"  {p['ticker']}: {p['side']} qty={p['quantity']} "
            f"TP={p['tp_price']} SL={p['sl_price']}"
        )

    if dry_run:
        print("Dry-run only. Re-run with --yes to submit to IBKR paper/live.")
        return 0

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "4002"))
    client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
    ib = await connect_ibkr(host=host, port=port, client_id=client_id)
    errors = 0
    try:
        for p in plan:
            try:
                result = await submit_protective_oca_orders(
                    ib,
                    p["ticker"],
                    p["side"],
                    p["quantity"],
                    tp_price=p["tp_price"],
                    sl_price=p["sl_price"],
                )
                print("OK", result)
                for oid, otype, px in (
                    (result.get("tp_order_id"), "LIMIT", p["tp_price"]),
                    (result.get("sl_order_id"), "STOP", p["sl_price"]),
                ):
                    if oid is None:
                        continue
                    cmd = InsertIbkrOrderCommand(
                        order_id=int(oid),
                        ticker=p["ticker"],
                        side="SELL" if p["side"] == "BUY" else "BUY",
                        quantity=p["quantity"],
                        order_type=otype,
                        limit_price=float(px) if otype == "LIMIT" and px is not None else None,
                        stop_price=float(px) if otype == "STOP" and px is not None else None,
                        parent_order_id=None,
                        status="submitted",
                        trade_signal_id="",
                        notes=f"protective_oca:{result.get('oca_group')}",
                    )
                    enqueue_typed_command(cmd, db_path=vault, user_id="ibkr-protective")
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"ERR {p['ticker']}: {exc}")
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    # Show open orders
    ib2 = await connect_ibkr(host=host, port=port, client_id=client_id + 10)
    try:
        trades = ib2.openTrades()
        print(f"open_trades={len(trades)}")
        for t in trades:
            o = t.order
            c = t.contract
            print(
                f"  {getattr(c, 'symbol', '?')} id={o.orderId} {o.action} {o.orderType} "
                f"qty={o.totalQuantity} lmt={getattr(o, 'lmtPrice', None)} "
                f"aux={getattr(o, 'auxPrice', None)} tif={o.tif} oca={getattr(o, 'ocaGroup', None)}"
            )
    finally:
        try:
            ib2.disconnect()
        except Exception:
            pass

    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        default=os.getenv(
            "IBKR_EXECUTE_ORDER_DB_PATH",
            "/root/Capadonna-Driller/db/private/1726618406/quant_traderdb1.duckdb",
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Actually submit to IBKR")
    parser.add_argument(
        "--tickers",
        default="",
        help="Comma-separated filter (default: all ACTIVE with position)",
    )
    args = parser.parse_args()
    _load_dotenv(Path("/root/duckclaw/.env"))
    _load_dotenv(Path.cwd() / ".env")
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None
    if not args.dry_run and not args.yes:
        print("Refusing to submit without --yes (or pass --dry-run).", file=sys.stderr)
        return 2
    return asyncio.run(_run(vault=args.vault, dry_run=args.dry_run, tickers=tickers))


if __name__ == "__main__":
    raise SystemExit(main())
