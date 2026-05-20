#!/usr/bin/env python3
"""Re-aplica Tailscale Serve :8443 → Next.js admin (detecta puerto activo)."""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def detect_admin_port() -> int:
    """Puerto donde responde GET /api/admin/health (Next BFF)."""
    raw = (os.environ.get("DUCKCLAW_ADMIN_PORT") or "").strip()
    candidates: list[int] = []
    if raw.isdigit():
        candidates.append(int(raw))
    for p in (3001, 3000, 3002):
        if p not in candidates:
            candidates.append(p)
    for port in candidates:
        url = f"http://127.0.0.1:{port}/api/admin/health"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return port
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return int(raw) if raw.isdigit() else 3000


def restore_admin_serve() -> int:
    port = detect_admin_port()
    script = REPO_ROOT / "scripts" / "tailscale_serve_admin.sh"
    if not script.is_file():
        print(f"error: no existe {script}", file=sys.stderr)
        return 1
    env = {**os.environ, "DUCKCLAW_ADMIN_PORT": str(port)}
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
    )
    print(f"ADMIN_SERVE_PORT={port}")
    return proc.returncode


def main() -> int:
    return restore_admin_serve()


if __name__ == "__main__":
    raise SystemExit(main())
