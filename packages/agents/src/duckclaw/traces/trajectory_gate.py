"""Gate tool-call sequences against a golden DAG: grade the path, not only the final text.

An agent can reach a right answer by hallucinating a tool or skipping the approval step. The golden file says which paths are legal::

    start: [read_sql, run_sandbox]            # first call of a turn
    edges: {read_sql: [read_sql, run_sandbox], run_sandbox: [], ...}   # tool -> tools that may follow it ([] = last call)
    forbidden: [drop_table]                   # never, anywhere
    requires_before: {write_record: [request_approval]}   # a call is legal only if these were called earlier in the turn

Trajectories are the ``tool_transitions`` JSONL records (one per call, see ``tool_transitions.py``), split per turn. Run it on any corpus, e.g. in a CI job of the repo that owns the agents::

    python -m duckclaw.traces.trajectory_gate golden.yaml corpus_dir_or_file.jsonl

Exit code 1 and one line per violation when a trajectory leaves the DAG.

``learn`` drafts the golden from a corpus you trust: ``python -m duckclaw.traces.trajectory_gate learn corpus [min_count]``. Tools and
edges seen fewer than ``min_count`` times (default 3) are left out, so a rare path counts as a deviation; ``forbidden`` and
``requires_before`` are judgement calls and stay yours to add.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml


def load_golden(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def check_trajectory(tools: list[str], golden: dict[str, Any]) -> list[str]:
    edges: dict[str, list[str]] = golden.get("edges") or {}
    forbidden = set(golden.get("forbidden") or [])
    required: dict[str, list[str]] = golden.get("requires_before") or {}
    out: list[str] = []
    for i, tool in enumerate(tools):
        if tool in forbidden:
            out.append(f"call {i + 1}: forbidden tool {tool}")
        elif tool not in edges:
            out.append(f"call {i + 1}: {tool} is not in the golden DAG (hallucinated or new tool)")
        elif i == 0 and tool not in (golden.get("start") or edges):
            out.append(f"call 1: {tool} may not open a turn")
        elif i and tool not in (edges.get(tools[i - 1]) or []):
            out.append(f"call {i + 1}: {tools[i - 1]} -> {tool} is not an edge of the golden DAG")
        missing = [r for r in required.get(tool, []) if r not in tools[:i]]
        if missing:
            out.append(f"call {i + 1}: {tool} ran without {', '.join(missing)} earlier in the turn")
    return out


def turns(records: Iterable[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """(label, tool names in call order) per turn. A record whose ``prior_calls`` is empty opens a new turn: the same request
    text repeats in one session (cron prompts), so (session, request) alone would glue unrelated turns together."""
    done: list[tuple[str, list[str]]] = []
    live: dict[tuple[str, str], list[str]] = {}
    for r in records:
        key = (str(r.get("session_id") or ""), str((r.get("context") or {}).get("request") or ""))
        if key not in live or not (r.get("context") or {}).get("prior_calls"):
            live[key] = []
            done.append((f"[{key[0] or '?'}] {key[1][:60]!r}", live[key]))
        live[key].append(str((r.get("action") or {}).get("tool") or ""))
    return done


def read_records(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    files = sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    return [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_corpus(records: Iterable[dict[str, Any]], golden: dict[str, Any]) -> list[str]:
    return [f"{label}: {v}" for label, tools in turns(records) for v in check_trajectory(tools, golden)]


def learn_golden(records: Iterable[dict[str, Any]], min_count: int = 3) -> dict[str, Any]:
    seen: Counter[str] = Counter()
    start: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for _, tools in turns(records):
        seen.update(tools)
        start[tools[0]] += 1
        pairs.update(zip(tools, tools[1:]))
    edges: dict[str, list[str]] = {t: [] for t, n in seen.items() if n >= min_count}
    for (a, b), n in sorted(pairs.items()):
        if n >= min_count and a in edges and b in edges:
            edges[a].append(b)
    return {"start": sorted(t for t, n in start.items() if n >= min_count and t in edges), "edges": dict(sorted(edges.items())),
            "forbidden": [], "requires_before": {}}


def main(argv: list[str]) -> int:
    if argv[:1] == ["learn"] and len(argv) in (2, 3):
        print(yaml.safe_dump(learn_golden(read_records(argv[1]), int(argv[2]) if len(argv) == 3 else 3), sort_keys=False))
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    records = read_records(argv[1])
    violations = check_corpus(records, load_golden(argv[0]))
    print(f"{len(turns(records))} trajectories, {len(violations)} violations")
    print("\n".join(violations))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
