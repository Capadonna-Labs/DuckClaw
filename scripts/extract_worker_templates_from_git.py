#!/usr/bin/env python3
"""Extract forge/templates worker dirs from a git commit (Windows-safe git show)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_COMMIT = "a085060"
DEFAULT_SOURCE = "packages/agents/src/duckclaw/forge/templates"
ROOT_FILES = (
    "entry_router.yaml",
    "manager_router.yaml",
)
WORKER_FILES = (
    "manifest.yaml",
    "manifest.yml",
    "system_prompt.md",
    "schema.sql",
    "seed_data.sql",
    "soul.md",
    "domain_closure.md",
    "security_policy.yaml",
    "homeostasis.yaml",
    "AGENT_OVERVIEW.md",
    "WORKER_OVERVIEW.md",
    "orchestrator_planner.md",
    "routing_table.yaml",
)


def _run(args: list[str], *, text: bool = False) -> str:
    return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=text)


def _list_tree(commit: str, path: str) -> list[str]:
    try:
        out = _run(["git", "ls-tree", "-r", "--name-only", f"{commit}:{path}"], text=True)
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _show_bytes(commit: str, path: str) -> bytes | None:
    try:
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return None


def extract_worker(
    commit: str,
    source_root: str,
    worker_id: str,
    dest_root: Path,
) -> int:
    tree_prefix = f"{source_root}/{worker_id}"
    listed = _list_tree(commit, tree_prefix)
    if listed:
        files = [
            f"{tree_prefix}/{name}" if "/" not in name and not name.startswith(tree_prefix) else (
                name if name.startswith(source_root) else f"{tree_prefix}/{name.lstrip('/')}"
            )
            for name in listed
        ]
    else:
        files = [f"{tree_prefix}/{name}" for name in WORKER_FILES]
    written = 0
    for repo_path in files:
        rel = repo_path[len(f"{source_root}/") :]
        data = _show_bytes(commit, repo_path)
        if data is None:
            continue
        out = dest_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        written += 1
    return written


def extract_root_files(commit: str, source_root: str, dest_root: Path) -> int:
    written = 0
    for name in ROOT_FILES:
        repo_path = f"{source_root}/{name}"
        data = _show_bytes(commit, repo_path)
        if data is None:
            continue
        out = dest_root / name
        out.write_bytes(data)
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DuckClaw worker templates from git history")
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument("--source-root", default=DEFAULT_SOURCE)
    parser.add_argument("--dest", required=True, help="Destination root (e.g. Capadonna-Driller/workers/duckclaw-templates)")
    parser.add_argument(
        "--worker",
        action="append",
        dest="workers",
        default=[],
        help="Worker directory name (repeatable). Empty = all non-system dirs at commit.",
    )
    parser.add_argument("--include-router-yaml", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    workers = list(args.workers)
    if not workers:
        try:
            names = _run(
                ["git", "ls-tree", "--name-only", f"{args.commit}:{args.source_root}"],
                text=True,
            ).splitlines()
        except subprocess.CalledProcessError as exc:
            print(f"Cannot list templates at {args.commit}: {exc}", file=sys.stderr)
            return 1
        skip = {"default", "industries", "workflows"}
        workers = [n.strip() for n in names if n.strip() and n.strip() not in skip]

    total = 0
    for worker_id in workers:
        n = extract_worker(args.commit, args.source_root, worker_id, dest)
        print(f"{worker_id}: {n} file(s)")
        total += n

    if args.include_router_yaml:
        total += extract_root_files(args.commit, args.source_root, dest)

    print(f"Wrote {total} file(s) under {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
