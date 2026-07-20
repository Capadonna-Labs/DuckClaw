#!/usr/bin/env python3
"""
Activa Tailscale + Funnel al puerto del gateway y re-registra webhooks de Telegram.

Uso (desde raíz del repo):
  uv run python scripts/start_telegram_ingress.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            if key and key not in os.environ:
                os.environ[key] = v.strip().strip("'\"")


def _funnel_already_on_port(port: int) -> bool:
    """Evita ``funnel reset`` si el funnel ya expone el puerto del gateway."""
    code, out, err = _run(["tailscale", "funnel", "status"], timeout=15)
    if code != 0:
        return False
    text = out + err
    markers = (f":{port}", f"127.0.0.1:{port}", f"localhost:{port}")
    return any(m in text for m in markers)


def _run(argv: list[str], *, timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def main() -> int:
    _load_dotenv()
    os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(REPO_ROOT))

    if not shutil.which("tailscale"):
        print("error: CLI tailscale no instalada. Instala Tailscale en este Mac.", file=sys.stderr)
        return 1

    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip()
    if ".ts.net" not in public:
        print(
            "warn: DUCKCLAW_PUBLIC_URL no es *.ts.net; Funnel puede no ser necesario.",
            file=sys.stderr,
        )

    from duckclaw.gateway_port import resolve_gateway_port

    port = resolve_gateway_port()
    chunks: list[str] = []

    print("── Tailscale up ──")
    code, out, err = _run(["tailscale", "up"], timeout=90)
    chunks.extend([out, err])
    if code != 0 and "already" not in (out + err).lower():
        print("\n".join(chunks), file=sys.stderr)
        print(
            f"error: tailscale up falló (código {code}). Abre la app Tailscale si hace falta.",
            file=sys.stderr,
        )
        return code or 1

    if _funnel_already_on_port(port):
        print(f"── Funnel ya activo en puerto {port} (sin reset) ──")
    else:
        print("── Funnel al gateway ──")
        code, out, err = _run(["tailscale", "funnel", "--bg", str(port)], timeout=60)
        chunks.extend([out, err])
        if code != 0:
            print("warn: funnel --bg falló; aplicando reset (borra Serve :8443 temporalmente)", file=sys.stderr)
            code, out, err = _run(["tailscale", "funnel", "reset"], timeout=30)
            chunks.extend([out, err])
            code, out, err = _run(["tailscale", "funnel", "--bg", str(port)], timeout=60)
            chunks.extend([out, err])
        if code != 0:
            print("\n".join(chunks))
            print(f"error: tailscale funnel --bg {port} falló", file=sys.stderr)
            return code or 1
        print(out or f"Funnel activo en puerto {port}")

    print("── Restaurar admin Serve (:8443) tras funnel ──")
    code, out, err = _run(
        ["uv", "run", "python", "scripts/restore_tailscale_admin_serve.py"],
        timeout=45,
    )
    print(out, err, sep="\n")
    if code != 0:
        print("warn: no se pudo restaurar Serve :8443; ejecuta restore_tailscale_admin_serve.py", file=sys.stderr)

    code, out, err = _run(["tailscale", "funnel", "status"], timeout=15)
    chunks.extend([out, err])
    print(out or err)

    print("── register_webhooks ──")
    code, out, err = _run(
        ["uv", "run", "python", "scripts/register_webhooks.py"],
        timeout=90,
    )
    print(out, err, sep="\n")
    if code != 0:
        return code

    print("── check_telegram_ingress ──")
    code, out, err = _run(
        ["uv", "run", "python", "scripts/check_telegram_ingress.py"],
        timeout=45,
    )
    print(out, err, sep="\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
