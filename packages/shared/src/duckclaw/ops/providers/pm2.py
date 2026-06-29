"""PM2 provider: detect pm2, run with current Python interpreter."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def resolve_pm2_executable() -> str | None:
    """
    Ruta absoluta al binario PM2.

    En Windows, ``shutil.which('pm2')`` suele devolver un shim sin extensión que
    ``CreateProcess`` no ejecuta; preferimos ``pm2.cmd`` en ``%APPDATA%\\npm``.
    """
    if platform.system() == "Windows":
        candidates: list[str] = []
        appdata = (os.environ.get("APPDATA") or "").strip()
        if appdata:
            npm_dir = Path(appdata) / "npm"
            for name in ("pm2.cmd", "pm2.exe", "pm2"):
                path = npm_dir / name
                if path.is_file():
                    candidates.append(str(path))
        for name in ("pm2.cmd", "pm2.exe", "pm2"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
        seen: set[str] = set()
        for path in candidates:
            norm = str(Path(path).resolve())
            if norm in seen:
                continue
            seen.add(norm)
            suffix = Path(path).suffix.lower()
            if suffix in (".cmd", ".exe"):
                return path
            cmd_sibling = Path(path).with_suffix(".cmd")
            if cmd_sibling.is_file():
                return str(cmd_sibling)
        return candidates[0] if candidates else None
    return shutil.which("pm2")


def pm2_argv(*args: str) -> list[str]:
    """Lista ``argv`` para ``subprocess`` con el ejecutable PM2 resuelto."""
    exe = resolve_pm2_executable()
    if not exe:
        return ["pm2", *args]
    return [exe, *args]


def is_pm2_available() -> bool:
    return resolve_pm2_executable() is not None


def deploy_pm2(
    name: str,
    command: str,
    python_path: str,
    cwd: str,
    **kwargs: Any,
) -> str:
    if not is_pm2_available():
        return "Error: pm2 is not installed or not in PATH. Install it (e.g. npm install -g pm2) and retry."

    args = pm2_argv("start", python_path, "--name", name, "--cwd", cwd, "--") + command.split()

    try:
        r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
        if r.returncode != 0:
            return f"Error: pm2 start failed. stderr: {r.stderr or r.stdout or 'unknown'}"
        return f"pm2: started '{name}'. Use 'pm2 logs {name}' and 'pm2 save' to persist."
    except Exception as e:
        return f"Error running pm2: {e}"
