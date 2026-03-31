"""Punto de entrada del Sovereign Wizard v2.0."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import materialize
from duckops.sovereign.ui import run_wizard_loop


def _find_repo_root(start: Path | None) -> Path:
    if start is None:
        start = Path.cwd()
    cur = start.resolve()
    for _ in range(8):
        if (cur / "packages" / "duckops").is_dir() and (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def run_sovereign_wizard(repo_root: Path | None = None) -> int:
    rr = _find_repo_root(repo_root)
    try:
        w = min(120, shutil.get_terminal_size().columns)
    except Exception:
        w = 100
    console = Console(width=w)
    draft = SovereignDraft()
    code = run_wizard_loop(rr, console, draft)
    if code == 2:

        def _print(msg: str) -> None:
            console.print(msg)

        return materialize(rr, draft, console_print=_print, deploy_pm2=True)
    return code
