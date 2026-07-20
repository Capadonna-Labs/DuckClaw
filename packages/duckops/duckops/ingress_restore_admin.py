"""Re-aplica Tailscale Serve :8443 → Next.js admin (detecta puerto activo)."""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request

from duckops.paths import repo_root


def _load_repo_dotenv() -> None:
    env_path = repo_root() / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")


def detect_admin_port() -> int:
    """Puerto del admin Next.js. Prioridad: DUCKCLAW_ADMIN_PORT en .env, luego health probe."""
    _load_repo_dotenv()
    raw = (os.environ.get("DUCKCLAW_ADMIN_PORT") or "").strip()
    if raw.isdigit():
        port = int(raw)
        url = f"http://127.0.0.1:{port}/login"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return port
        except (urllib.error.URLError, TimeoutError, OSError):
            print(
                f"warning: DUCKCLAW_ADMIN_PORT={port} configurado pero Next no responde en /login; "
                f"Serve apuntará igual a :{port} (arranca pnpm dev antes).",
                file=sys.stderr,
            )
        return port

    for port in (3001, 3000, 3002):
        url = f"http://127.0.0.1:{port}/login"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return port
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return 3001


def restore_admin_serve() -> int:
    port = detect_admin_port()
    root = repo_root()
    proc = subprocess.run(
        [
            "tailscale",
            "serve",
            "--bg",
            "--https=8443",
            f"http://127.0.0.1:{port}",
        ],
        cwd=root,
        env={**os.environ, "DUCKCLAW_ADMIN_PORT": str(port)},
        text=True,
    )
    print(f"ADMIN_SERVE_PORT={port}")
    return proc.returncode


def main() -> int:
    return restore_admin_serve()


if __name__ == "__main__":
    raise SystemExit(main())
