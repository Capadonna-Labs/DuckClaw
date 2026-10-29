"""Gate tool-call sequences against a golden DAG: grade the path, not only the final text.

An agent can reach a right answer by hallucinating a tool or skipping the approval step. The golden file says which paths are legal::

    start: [read_sql, run_sandbox]            # first call of a turn
    edges: {read_sql: [read_sql, run_sandbox], run_sandbox: [], ...}   # tool -> tools that may follow it ([] = last call)
    forbidden: [drop_table]                   # never, anywhere
    requires_before: {write_record: [request_approval]}   # a call is legal only if these were called earlier in the turn

Trajectories are the ``tool_transitions`` JSONL records (one per call, see ``tool_transitions.py``), grouped per turn by
(session_id, request). Run it on any corpus, e.g. in a CI job of the repo that owns the agents::

    python -m duckclaw.traces.trajectory_gate golden.yaml corpus_dir_or_file.jsonl

Exit code 1 and one line per violation when a trajectory leaves the DAG.
"""

from __future__ import annotations

import json
import sys
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


def turns(records: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Tool names per turn, in call order."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for r in records:
        key = (str(r.get("session_id") or ""), str((r.get("context") or {}).get("request") or ""))
        grouped.setdefault(key, []).append(str((r.get("action") or {}).get("tool") or ""))
    return grouped


def read_records(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    files = sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    return [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_corpus(records: Iterable[dict[str, Any]], golden: dict[str, Any]) -> list[str]:
    return [f"[{sid or '?'}] {req[:60]!r}: {v}" for (sid, req), tools in turns(records).items() for v in check_trajectory(tools, golden)]


def main(argv: list[str]) -> int:
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
