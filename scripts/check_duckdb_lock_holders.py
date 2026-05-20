#!/usr/bin/env python3
"""Detecta procesos que mantienen locks en bóvedas DuckDB bajo db/private (salida JSON)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else Path(__file__).resolve().parent.parent


def _pm2_pids() -> set[int]:
    try:
        out = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return set()
        data = json.loads(out.stdout)
        pids: set[int] = set()
        for proc in data:
            pid = proc.get("pid")
            if isinstance(pid, int) and pid > 0:
                pids.add(pid)
        return pids
    except Exception:
        return set()


def _lsof_private_dbs(private_dir: Path) -> list[dict[str, str | int]]:
    if not private_dir.is_dir():
        return []
    dbs = sorted(private_dir.glob("*/*.duckdb"))
    if not dbs:
        return []
    holders: list[dict[str, str | int]] = []
    pm2 = _pm2_pids()
    for db_path in dbs:
        try:
            proc = subprocess.run(
                ["lsof", str(db_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except FileNotFoundError:
            return holders
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            cmd = parts[0]
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if pid in pm2:
                continue
            command = ""
            try:
                ps = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                command = (ps.stdout or "").strip()
            except Exception:
                command = cmd
            kind = "unknown"
            low = command.lower()
            if "pytest" in low:
                kind = "pytest"
            elif "duckclaw" in low or "db-writer" in low:
                kind = "duckclaw"
            holders.append(
                {
                    "pid": pid,
                    "db": str(db_path.relative_to(_repo_root())),
                    "command": command[:240],
                    "kind": kind,
                }
            )
    return holders


def main() -> int:
    repo = _repo_root()
    private = repo / "db" / "private"
    blocking = _lsof_private_dbs(private)
    payload = {"blocking": blocking, "repo": str(repo)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
