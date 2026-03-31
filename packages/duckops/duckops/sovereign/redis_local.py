"""Intento de Redis local gestionado (spec §5 — brew / apt)."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


def try_start_redis_local(repo_root: Path) -> tuple[bool, str]:
    """
    macOS: ``brew services start redis`` si brew existe.
    Linux: mensaje para ``apt install redis-server`` / systemctl (no forzar sudo).
    """
    system = platform.system()
    if system == "Darwin":
        brew = shutil.which("brew")
        if not brew:
            return False, "Homebrew no encontrado; instala Redis manualmente o usa Docker."
        try:
            r = subprocess.run(
                [brew, "services", "start", "redis"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(repo_root),
            )
            out = (r.stdout or r.stderr or "").strip()
            if r.returncode == 0:
                return True, out or "brew services start redis: OK"
            return False, f"brew falló ({r.returncode}): {out[:500]}"
        except Exception as e:
            return False, str(e)[:500]

    if system == "Linux":
        return (
            False,
            "En Linux: sudo apt install redis-server && sudo systemctl enable --now redis-server "
            "(o usa Docker). No se ejecutó sudo desde el wizard.",
        )

    return False, "SO no soportado para auto-arranque de Redis."
