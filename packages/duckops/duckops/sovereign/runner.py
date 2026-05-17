"""Punto de entrada del Sovereign Wizard v2.0."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.debug_ndjson import agent_log
from duckops.sovereign.materialize import load_draft_json, materialize
from duckops.sovereign.tui_chat import run_tui_chat
from duckops.sovereign.tui_shell import TuiShell
from duckops.sovereign.ui import run_wizard_loop
from duckops.sovereign.wizard_reset import default_worker_for_fresh, fresh_sovereign_draft
from duckops.sovereign.workers_catalog import list_worker_picks


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


def run_sovereign_chat(repo_root: Path | None = None) -> int:
    """Chat TUI contra playground admin (sin recorrer el wizard)."""
    rr = _find_repo_root(repo_root)
    try:
        w = min(120, shutil.get_terminal_size().columns)
    except Exception:
        w = 100
    console = Console(width=w)
    # #region agent log
    agent_log(
        location="runner.py:run_sovereign_chat",
        message="enter chat",
        hypothesis_id="H1-import",
    )
    # #endregion
    saved = load_draft_json()
    draft = saved if saved is not None else SovereignDraft()
    return run_tui_chat(rr, draft, console=console)


def run_sovereign_wizard(repo_root: Path | None = None, *, manual: bool = False) -> int:
    rr = _find_repo_root(repo_root)
    try:
        w = min(120, shutil.get_terminal_size().columns)
    except Exception:
        w = 100
    console = Console(width=w)
    picks = list_worker_picks(rr)
    draft = fresh_sovereign_draft(
        worker_id=default_worker_for_fresh([p.worker_id for p in picks]),
    )
    code, shell = run_wizard_loop(rr, console, draft, manual=manual)
    if code == 2:

        def _print(msg: str) -> None:
            console.print(msg)

        with shell.render_live_working("Aplicando configuración"):
            mat_code = materialize(rr, draft, console_print=_print, deploy_pm2=True)
        TuiShell.print_deploy_next_steps(console, draft)
        if mat_code == 0:
            try:
                ans = console.input(
                    "\n[bold]¿Abrir chat con agentes en esta terminal?[/] [dim][y/N][/]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = ""
            if ans in ("y", "s", "sí", "si", "yes"):
                return run_tui_chat(rr, draft, console=console)
        return mat_code
    return code
