"""Arranca backend, admin de producción y el correo de estado del Mac."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from duckclaw.ops.stack_deploy import run_stack_deploy
from duckclaw.ops.toolchain import ToolchainError, run_pm2

PrintFn = Callable[[str], None]

_ADMIN_NAME = "duckclaw-admin-ui"
_HOST_STATUS_NAME = "DuckClaw-Host-Status"


def _start_or_restart(repo_root: Path, ecosystem_name: str, process_name: str, print_fn: PrintFn) -> None:
    ecosystem = repo_root / "config" / ecosystem_name
    proc = run_pm2("start", str(ecosystem), "--only", process_name, "--update-env", cwd=repo_root)
    if proc.returncode == 0:
        print_fn(f"PM2 {process_name} en marcha")
        return
    detail = (proc.stderr or proc.stdout or "").strip()
    if "already" not in detail.lower():
        raise ToolchainError(detail or f"PM2 no arrancó {process_name}")
    restarted = run_pm2("restart", process_name, "--update-env", cwd=repo_root)
    if restarted.returncode != 0:
        raise ToolchainError((restarted.stderr or restarted.stdout or process_name).strip())
    print_fn(f"PM2 {process_name} reiniciado")


def _build_admin(repo_root: Path, print_fn: PrintFn) -> int:
    print_fn("==> Build admin producción (puerto 3001, sin el lint ya roto del repo)")
    proc = subprocess.run(
        ["pnpm", "--dir", "apps/duckclaw-admin", "exec", "next", "build", "--no-lint"],
        cwd=repo_root,
        check=False,
    )
    return proc.returncode


def run_serve_mac(*, repo_root: Path, print_fn: PrintFn) -> int:
    code = run_stack_deploy(
        repo_root=repo_root,
        print_fn=print_fn,
        sync_deps=True,
        migrate=True,
        host="127.0.0.1",
        port=8000,
        wait_health=True,
        health_timeout=45.0,
        full=False,
    )
    if code != 0:
        return code
    build_code = _build_admin(repo_root, print_fn)
    if build_code != 0:
        return build_code
    _start_or_restart(repo_root, "ecosystem.admin-ui.config.cjs", _ADMIN_NAME, print_fn)
    _start_or_restart(repo_root, "ecosystem.host-status.config.cjs", _HOST_STATUS_NAME, print_fn)
    saved = run_pm2("save", cwd=repo_root)
    if saved.returncode != 0:
        print_fn((saved.stderr or saved.stdout or "pm2 save falló").strip())
        return saved.returncode
    print_fn("Listo. Backend, admin :3001 y correo cada 3 horas quedan en PM2.")
    return 0
