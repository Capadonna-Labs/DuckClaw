#!/usr/bin/env python3
"""Place protective GTC TP/SL (OCA) for existing IBKR positions with ACTIVE levels.

Does NOT send a new market entry — only closing Limit (TP) + Stop (SL).

Usage:
  uv run python scripts/place_protective_gtc_brackets.py --dry-run
  uv run python scripts/place_protective_gtc_brackets.py --yes

Use a stable IBKR_CLIENT_ID (default 90) so cancel-before-replace can cancel
orders this script previously placed (IBKR cancels are per-client).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# ib_insync + nest_asyncio: avoid "This event loop is already running"
try:
    import nest_asyncio

    nest_asyncio.apply()
except Exception:
    pass
try:
    from ib_insync import util as ib_util

    ib_util.patchAsyncio()
except Exception:
    pass


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _latest_active_levels(rows: list[tuple]) -> dict[str, tuple[float | None, float | None]]:
    """Keep newest ACTIVE row per ticker (rows ordered ticker, created_at DESC)."""
    out: dict[str, tuple[float | None, float | None]] = {}
    for ticker, tp, sl, *_rest in rows:
        t = str(ticker).upper()
        if t in out:
            continue
        out[t] = (
            float(tp) if tp is not None else None,
            float(sl) if sl is not None else None,
        )
    return out


def _sl_too_close(*, side: str, ref: float | None, sl: float | None, min_pct: float) -> bool:
    if ref is None or sl is None or ref <= 0 or min_pct <= 0:
        return False
    dist = abs(float(ref) - float(sl)) / float(ref)
    return dist < min_pct


async def _live_ibkr_qty(ib, ticker: str) -> float | None:
    """Prefer live IBKR position qty over vault cache (IEF stale row incident)."""
    try:
        for p in list(ib.positions() or []):
            sym = str(getattr(getattr(p, "contract", None), "symbol", "") or "").upper()
            if sym == ticker:
                return float(p.position)
    except Exception:
        return None
    return None


async def _run(
    *,
    vault: str,
    dry_run: bool,
    tickers: list[str] | None,
    min_sl_distance_pct: float,
    replace_existing: bool,
) -> int:
    import duckdb

    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.ibkr_bracket_orders import (
        cancel_protective_orders_for_ticker,
        connect_ibkr,
        submit_protective_oca_orders,
    )
    from duckclaw.write_commands import InsertIbkrOrderCommand

    con = duckdb.connect(vault, read_only=True)
    try:
        levels_rows = con.execute(
            """
            SELECT ticker, take_profit, stop_loss, created_at, approved_at
            FROM quant_core.tp_sl_levels
            WHERE upper(cast(status AS VARCHAR)) = 'ACTIVE'
            ORDER BY ticker, coalesce(approved_at, created_at) DESC, created_at DESC
            """
        ).fetchall()
        vault_positions = {
            str(r[0]).upper(): {
                "qty": float(r[1]),
                "avg": float(r[2]) if r[2] is not None else None,
                "mark": float(r[3]) if r[3] is not None else None,
            }
            for r in con.execute(
                """
                SELECT ticker, qty, avg_entry_price, current_price
                FROM quant_core.portfolio_positions
                WHERE qty != 0
                """
            ).fetchall()
        }
    finally:
        con.close()

    levels = _latest_active_levels(levels_rows)

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "4002"))
    # Stable default: IBKR cancels are per-client; ephemeral ids cannot cancel prior places.
    client_id = int(os.getenv("IBKR_CLIENT_ID", "90"))

    # Live qty when possible (even on dry-run) so plan matches broker.
    live_qty: dict[str, float] = {}
    ib_probe = None
    try:
        ib_probe = await connect_ibkr(host=host, port=port, client_id=client_id + 20)
        for t in levels:
            q = await _live_ibkr_qty(ib_probe, t)
            if q is not None and abs(q) > 1e-9:
                live_qty[t] = q
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: IBKR live positions unavailable ({exc}); using vault qty")
    finally:
        if ib_probe is not None:
            try:
                ib_probe.disconnect()
            except Exception:
                pass

    plan: list[dict] = []
    for t, (tp_f, sl_f) in levels.items():
        if tickers and t not in tickers:
            continue
        qty = live_qty.get(t)
        src = "ibkr"
        if qty is None:
            row = vault_positions.get(t)
            if row is None:
                print(f"SKIP {t}: ACTIVE tp/sl but no IBKR/vault position")
                continue
            qty = float(row["qty"])
            src = "vault"
            if t not in live_qty and live_qty:
                # We successfully listed IBKR positions and this ticker is absent.
                print(f"SKIP {t}: ACTIVE in vault but not in IBKR positions (stale vault row)")
                continue
        if abs(qty) < 1e-9:
            print(f"SKIP {t}: zero qty")
            continue
        side = "BUY" if qty > 0 else "SELL"
        vault_row = vault_positions.get(t) or {}
        ref = vault_row.get("mark") or vault_row.get("avg")
        if ref is not None and tp_f is not None and sl_f is not None:
            if side == "BUY" and not (sl_f < ref < tp_f):
                print(
                    f"SKIP {t}: ref/mark={ref} not between SL={sl_f} and TP={tp_f} "
                    "(stop would fire immediately or RR invalid)"
                )
                continue
            if side == "SELL" and not (tp_f < ref < sl_f):
                print(
                    f"SKIP {t}: ref/mark={ref} not between TP={tp_f} and SL={sl_f} "
                    "(stop would fire immediately or RR invalid)"
                )
                continue
        if _sl_too_close(side=side, ref=ref if isinstance(ref, (int, float)) else None, sl=sl_f, min_pct=min_sl_distance_pct):
            print(
                f"SKIP {t}: SL={sl_f} within {min_sl_distance_pct:.2%} of mark/avg={ref} "
                "(raise --min-sl-distance-pct to override)"
            )
            continue
        plan.append(
            {
                "ticker": t,
                "side": side,
                "quantity": int(abs(qty)),
                "tp_price": tp_f,
                "sl_price": sl_f,
                "qty_source": src,
            }
        )

    if not plan:
        print("Nothing to place.")
        return 1

    print("Plan (protective GTC OCA — no new entry):")
    for p in plan:
        print(
            f"  {p['ticker']}: {p['side']} qty={p['quantity']} ({p['qty_source']}) "
            f"TP={p['tp_price']} SL={p['sl_price']}"
        )

    if dry_run:
        print("Dry-run only. Re-run with --yes to submit to IBKR paper/live.")
        return 0

    ib = await connect_ibkr(host=host, port=port, client_id=client_id)
    errors = 0
    try:
        for p in plan:
            try:
                if replace_existing:
                    cancelled = await cancel_protective_orders_for_ticker(ib, p["ticker"])
                    if cancelled:
                        print(f"CANCELLED {p['ticker']}: {cancelled} open order(s)")
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
    parser.add_argument(
        "--min-sl-distance-pct",
        type=float,
        default=0.005,
        help="Skip if |mark-SL|/mark < this (default 0.5%%); avoids near-trigger SL",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Do not cancel existing open orders for the ticker before placing",
    )
    args = parser.parse_args()
    _load_dotenv(Path("/root/duckclaw/.env"))
    _load_dotenv(Path.cwd() / ".env")
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None
    if not args.dry_run and not args.yes:
        print("Refusing to submit without --yes (or pass --dry-run).", file=sys.stderr)
        return 2
    return asyncio.run(
        _run(
            vault=args.vault,
            dry_run=args.dry_run,
            tickers=tickers,
            min_sl_distance_pct=max(0.0, float(args.min_sl_distance_pct)),
            replace_existing=not args.no_replace,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
