"""Arranque de la consola admin Next.js en desarrollo (pnpm)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

PrintFn = Callable[[str], None]

_ADMIN_DIR_REL = Path("apps") / "duckclaw-admin"
_DEFAULT_ADMIN_PORT = 3001


def _default_print(msg: str) -> None:
    print(msg, flush=True)


def admin_app_dir(repo_root: Path) -> Path:
    return (repo_root / _ADMIN_DIR_REL).resolve()


def resolve_admin_port(repo_root: Path) -> int:
    """Puerto HTTP de la consola admin (PORT en .env.local o default 3001)."""
    env_local = admin_app_dir(repo_root) / ".env.local"
    if env_local.is_file():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PORT="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                if raw.isdigit():
                    return int(raw)
    raw = (os.environ.get("PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return _DEFAULT_ADMIN_PORT


def admin_login_url(repo_root: Path) -> str:
    port = resolve_admin_port(repo_root)
    return f"http://127.0.0.1:{port}/login"


def ensure_admin_pnpm_deps(repo_root: Path, print_fn: PrintFn = _default_print) -> bool:
    admin_dir = admin_app_dir(repo_root)
    if not admin_dir.is_dir():
        print_fn(f"No existe {admin_dir}")
        return False
    pnpm = shutil.which("pnpm")
    if not pnpm:
        print_fn("pnpm no está en PATH; ejecuta duckops bootstrap --yes.")
        return False
    if (admin_dir / "node_modules").is_dir():
        return True
    print_fn("pnpm install en apps/duckclaw-admin (primera vez, puede tardar)...")
    code = subprocess.run(
        [pnpm, "install"],
        cwd=str(admin_dir),
        check=False,
    ).returncode
    return code == 0


def wait_admin_http(port: int, *, timeout_seconds: float = 120.0) -> bool:
    url = f"http://127.0.0.1:{port}/login"
    deadline = time.monotonic() + max(timeout_seconds, 1.0)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if 200 <= int(response.status) < 500:
                    return True
        except (OSError, urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.75)
    return False


def start_admin_dev_server(
    repo_root: Path,
    *,
    print_fn: PrintFn = _default_print,
) -> subprocess.Popen[bytes] | None:
    """Arranca ``pnpm dev`` en segundo plano."""
    admin_dir = admin_app_dir(repo_root)
    if not ensure_admin_pnpm_deps(repo_root, print_fn):
        return None
    pnpm = shutil.which("pnpm")
    if not pnpm:
        return None
    port = resolve_admin_port(repo_root)
    log_path = repo_root / ".duckclaw" / "admin-dev.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    print_fn(f"Consola admin → pnpm dev (puerto {port}, log {log_path})")
    env = os.environ.copy()
    env.setdefault("PORT", str(port))
    try:
        proc = subprocess.Popen(
            [pnpm, "dev"],
            cwd=str(admin_dir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        print_fn(f"No se pudo arrancar admin dev: {exc}")
        log_file.close()
        return None
    return proc


def open_admin_browser(repo_root: Path, print_fn: PrintFn = _default_print) -> None:
    url = admin_login_url(repo_root)
    print_fn(f"Abriendo navegador → {url}")
    try:
        webbrowser.open(url)
    except Exception as exc:
        print_fn(f"No se pudo abrir el navegador: {exc}. Abre manualmente: {url}")


def ensure_admin_web_ready(
    repo_root: Path,
    print_fn: PrintFn = _default_print,
    *,
    wait_seconds: float = 120.0,
) -> bool:
    """Arranca la consola Next si hace falta y espera hasta que responda HTTP."""
    port = resolve_admin_port(repo_root)
    if wait_admin_http(port, timeout_seconds=2.0):
        return True
    proc = start_admin_dev_server(repo_root, print_fn=print_fn)
    if proc is None:
        return False
    if wait_admin_http(port, timeout_seconds=wait_seconds):
        return True
    print_fn(f"Admin aún no responde en :{port}. Log: .duckclaw/admin-dev.log")
    return False

