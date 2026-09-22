#!/usr/bin/env python3
"""Backfill quant_core.closed_trades via InsertClosedTradeCommand (JSONL).

Each line is a Capadonna ``draft_to_mutation``-shaped object::

    {"ticker":"AAPL","fill_id":"...","closed_at":"...","qty":10,"entry_px":100,
     "exit_px":101,"pnl":10,"ret_pct":0.01,"side":"LONG","session_uid":"","signal_id":""}

Usage::

    uv run python scripts/backfill_closed_trades_jsonl.py \\
      --db-path /path/to/quant_traderdb1.duckdb \\
      --jsonl closes.jsonl \\
      --user-id 1726618406
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db-path", required=True, help="Target vault DuckDB path")
    p.add_argument("--jsonl", required=True, type=Path, help="JSONL of closed-trade mutations")
    p.add_argument("--user-id", default="default")
    p.add_argument("--tenant-id", default="default")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate rows only; do not enqueue",
    )
    args = p.parse_args(argv)

    from duckclaw.closed_trade_enqueue import (
        closed_trade_command_from_mutation,
        enqueue_closed_trade_recorded,
    )
    from duckclaw.schema_migrations import ensure_closed_trades_schema

    ensure_closed_trades_schema(args.db_path)

    ok = 0
    skipped = 0
    for i, line in enumerate(args.jsonl.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            mut = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"line {i}: JSON error: {exc}", file=sys.stderr)
            skipped += 1
            continue
        if not isinstance(mut, dict):
            print(f"line {i}: expected object", file=sys.stderr)
            skipped += 1
            continue
        try:
            closed_trade_command_from_mutation(mut, tenant_id=args.tenant_id)
        except Exception as exc:  # noqa: BLE001
            print(f"line {i}: invalid mutation: {exc}", file=sys.stderr)
            skipped += 1
            continue
        if args.dry_run:
            ok += 1
            continue
        tid = enqueue_closed_trade_recorded(
            mut,
            db_path=args.db_path,
            user_id=args.user_id,
            tenant_id=args.tenant_id,
        )
        if tid:
            ok += 1
            print(f"line {i}: enqueued task_id={tid}")
        else:
            skipped += 1
            print(f"line {i}: skipped (incomplete)", file=sys.stderr)

    print(f"done ok={ok} skipped={skipped} dry_run={args.dry_run}")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
