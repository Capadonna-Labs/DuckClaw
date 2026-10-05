#!/usr/bin/env python3
"""Build the tool-outcome dataset (context -> action -> outcome) and print the baseline.

Sources: conversation traces (backfill, SFT ``messages`` format) and live
``tool_transitions`` (written by tools_node). Overlapping rows are deduplicated.

    uv run python scripts/build_tool_outcome_dataset.py --out /path/tool_outcomes.jsonl
    uv run python scripts/build_tool_outcome_dataset.py --since 2026-09-01 --report-only
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any, Iterator

from duckclaw.graphs.conversation_traces import get_conversation_traces_dir
from duckclaw.traces.tool_transitions import build_transitions, tool_transitions_dir


def _jsonl(root: Path, name: str, since: str) -> Iterator[dict[str, Any]]:
    for path in sorted(root.glob(f"*/*/*/{name}")):
        day = "-".join(path.parts[-4:-1])
        if since and day < since:
            continue
        for line in path.open(encoding="utf-8", errors="replace"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def collect(traces: Path, transitions: Path, since: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()

    def _add(rec: dict[str, Any], source: str) -> None:
        key = (
            rec.get("session_id", ""),
            rec["action"]["tool"],
            rec["action"]["args"],
            rec["outcome"]["content_head"][:200],
        )
        if key in seen:
            return
        seen.add(key)
        rows.append({**rec, "source": source})

    for rec in _jsonl(transitions, "transitions.jsonl", since):
        _add(rec, "live")
    for trace in _jsonl(traces, "traces.jsonl", since):
        for rec in build_transitions(
            trace.get("messages") or [],
            session_id=str(trace.get("session_id") or ""),
            worker_id=str(trace.get("worker_id") or ""),
            timestamp=str(trace.get("timestamp") or ""),
        ):
            _add(rec, "trace")
    return rows


def report(rows: list[dict[str, Any]]) -> str:
    tot: collections.Counter[str] = collections.Counter()
    err: collections.Counter[str] = collections.Counter()
    kinds: collections.Counter[str] = collections.Counter()
    by_worker: collections.Counter[str] = collections.Counter()
    by_worker_err: collections.Counter[str] = collections.Counter()
    for r in rows:
        tool, out = r["action"]["tool"], r["outcome"]
        tot[tool] += 1
        by_worker[r.get("worker_id") or "?"] += 1
        if out["status"] == "error":
            err[tool] += 1
            kinds[out["error_kind"]] += 1
            by_worker_err[r.get("worker_id") or "?"] += 1
    n, e = sum(tot.values()), sum(err.values())
    lines = [f"transitions={n} errors={e} ({e / max(n, 1):.1%})", "", "by tool (top 15):"]
    lines += [f"  {t:36s} {c:6d}  err {err[t] / c:6.1%}" for t, c in tot.most_common(15)]
    lines += ["", "error kinds:"] + [f"  {k:16s} {c:6d}" for k, c in kinds.most_common()]
    lines += ["", "by worker:"] + [
        f"  {w:24s} {c:6d}  err {by_worker_err[w] / c:6.1%}" for w, c in by_worker.most_common(10)
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--traces", type=Path, default=get_conversation_traces_dir())
    p.add_argument("--transitions", type=Path, default=tool_transitions_dir())
    p.add_argument("--since", default="", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--out", type=Path, help="Output JSONL (dataset rows)")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)

    rows = collect(args.traces, args.transitions, args.since)
    print(report(rows))
    if args.out and not args.report_only:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(rows)} rows -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
