#!/usr/bin/env python3
"""Patch Capadonna broker_execute_signal: never coerce BRACKET → ENTRY market.

Root cause of Error #2 (XLU double-buy): the execute hook did::

    if st not in ("ENTRY", "EXIT"):
        st = "ENTRY"

so ``signal_type=BRACKET`` became a market buy. This patch refuses protective
types and points operators at ``execute_protective_oca_for_signal`` / TWS.

Applies on the Capadonna-Driller tree (VPS). Safe to re-run (idempotent marker).

Usage (on VPS)::

    python scripts/patch_capadonna_broker_execute_bracket.py \\
      --root /root/Capadonna-Driller
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "duckclaw.BLOCKED_PROTECTIVE_ORDER_ROUTE"

# Historical coercion (Error #2).
OLD_COERCE = '''        st = str(d.get("signal_type") or "ENTRY").strip().upper()
        if st not in ("ENTRY", "EXIT"):
            st = "ENTRY"
        return _WeightPlan(ticker=tkr, signal_type=st, weight_pct=w)'''

NEW_COERCE = '''        st = str(d.get("signal_type") or "ENTRY").strip().upper()
        # duckclaw.BLOCKED_PROTECTIVE_ORDER_ROUTE — never coerce BRACKET/OCA → ENTRY
        _protective = {
            "BRACKET", "OCA", "PROTECTIVE", "PROTECT", "PROTECTIVE_OCA",
            "PROTECT_OCA", "TP_SL", "TPSL",
        }
        if st in _protective or "BRACKET" in st or "PROTECT" in st:
            _emit(
                {
                    "status": "error",
                    "error": "BLOCKED_PROTECTIVE_ORDER_ROUTE",
                    "signal_type": st,
                    "message": (
                        f"signal_type={st} is protective OCA (TP/SL only), not a "
                        "market entry. Use submit_protective_oca_orders / "
                        "place_protective_gtc_brackets.py / TWS. Do not coerce to ENTRY."
                    ),
                },
                rc=1,
            )
        if st not in ("ENTRY", "EXIT"):
            _emit(
                {
                    "status": "error",
                    "message": f"signal_type desconocido: {st} (solo ENTRY|EXIT)",
                },
                rc=1,
            )
        return _WeightPlan(ticker=tkr, signal_type=st, weight_pct=w)'''

# Also refuse after plan is resolved from DB (DB path may return BRACKET raw).
OLD_WEIGHT_BRANCH = '''        ticker = plan.ticker
        signal_type = plan.signal_type
        weight_pct = plan.weight_pct
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)'''

NEW_WEIGHT_BRANCH = '''        ticker = plan.ticker
        signal_type = plan.signal_type
        weight_pct = plan.weight_pct
        # duckclaw.BLOCKED_PROTECTIVE_ORDER_ROUTE
        _st_up = str(signal_type or "").strip().upper()
        if _st_up in {
            "BRACKET", "OCA", "PROTECTIVE", "PROTECT", "PROTECTIVE_OCA",
            "PROTECT_OCA", "TP_SL", "TPSL",
        } or "BRACKET" in _st_up or "PROTECT" in _st_up:
            _emit(
                {
                    "status": "error",
                    "error": "BLOCKED_PROTECTIVE_ORDER_ROUTE",
                    "signal_type": _st_up,
                    "message": (
                        "Refuse market order for protective signal_type. "
                        "Place OCA via submit_protective_oca_orders / TWS."
                    ),
                },
                rc=1,
            )
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)'''


def _candidates(root: Path) -> list[Path]:
    return [
        root / "scripts" / "capadonna" / "broker_execute_signal.py",
        root / "workers" / "duckclaw" / "lib" / "broker_execute_signal.py",
        root / "services" / "ibkr-ohlcv-api" / "broker_execute_signal.py",
        root / "broker_execute_signal.py",
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: root not a directory: {root}")
        return 2

    targets = [p for p in _candidates(root) if p.is_file()]
    if not targets:
        print("ERROR: broker_execute_signal.py not found under", root)
        for p in _candidates(root):
            print("  looked:", p)
        return 2

    changed = 0
    for target in targets:
        text = target.read_text(encoding="utf-8")
        if MARKER in text and "BLOCKED_PROTECTIVE_ORDER_ROUTE" in text:
            print(f"OK (already patched): {target}")
            continue
        orig = text
        if OLD_COERCE in text:
            text = text.replace(OLD_COERCE, NEW_COERCE, 1)
        if OLD_WEIGHT_BRANCH in text and "Refuse market order for protective" not in text:
            text = text.replace(OLD_WEIGHT_BRANCH, NEW_WEIGHT_BRANCH, 1)
        if text == orig:
            print(f"WARN: no known coercion snippet in {target} — manual review needed")
            continue
        target.write_text(text, encoding="utf-8")
        changed += 1
        print(f"PATCHED: {target}")

    print(f"done: {changed} file(s) patched")
    return 0 if changed or any(MARKER in p.read_text(encoding="utf-8") for p in targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
