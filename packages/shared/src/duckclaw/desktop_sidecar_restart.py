"""Desktop lite: reiniciar sidecar embebido sin PM2/duckops."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _localappdata() -> Path:
    raw = (os.environ.get("LOCALAPPDATA") or "").strip()
    if not raw:
        raw = str(Path.home() / "AppData" / "Local")
    return Path(raw)


def desktop_backend_exe() -> Path:
    return _localappdata() / "DuckClaw" / "duckclaw_backend.exe"


async def _wait_health(base: str, timeout_sec: float = 90.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_sec
    url = f"{base.rstrip('/')}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        await asyncio.sleep(1.5)
    return False


async def restart_desktop_sidecar() -> dict[str, Any]:
    exe = desktop_backend_exe()
    chunks: list[str] = ["── Modo desktop lite (gateway) ──\n"]
    if not exe.is_file():
        return {
            "ok": False,
            "exit_code": 1,
            "stdout": "".join(chunks),
            "stderr": f"No se encontró {exe}. Copia duckclaw_backend.exe a %LOCALAPPDATA%\\DuckClaw\\.",
            "executed_via": "gateway-desktop",
        }

    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_exec(
            "taskkill",
            "/F",
            "/IM",
            "duckclaw_backend.exe",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        chunks.append("── taskkill duckclaw_backend.exe ──\nOK\n")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            listed = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq duckclaw_backend.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if "duckclaw_backend.exe" not in (listed.stdout or "").lower():
                break
            await asyncio.sleep(0.5)

    await asyncio.sleep(0.8)

    env = os.environ.copy()
    env_path = _localappdata() / "DuckClaw" / "desktop.env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    env["LITE_MODE"] = "1"
    env["DUCKCLAW_SPAWN_PROFILE"] = "1"
    env.setdefault("DUCKCLAW_DISABLE_DOTENV", "1")

    subprocess.Popen(  # noqa: S603 — desktop sidecar relaunch
        [str(exe)],
        cwd=str(exe.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    chunks.append(f"── Arrancando sidecar ──\n{exe}\n")

    host = (os.environ.get("DUCKCLAW_GATEWAY_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.environ.get("DUCKCLAW_GATEWAY_PORT") or "8000").strip() or "8000"
    healthy = await _wait_health(f"http://{host}:{port}")
    if healthy:
        chunks.append("\nGateway listo.\n")
    else:
        chunks.append("\n⚠ /health no respondió en 90s.\n")

    return {
        "ok": healthy,
        "exit_code": 0 if healthy else 2,
        "stdout": "".join(chunks),
        "stderr": "" if healthy else "Sidecar no respondió en :8000.",
        "executed_via": "gateway-desktop",
    }
