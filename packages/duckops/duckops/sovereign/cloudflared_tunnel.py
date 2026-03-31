"""Quick Tunnel de Cloudflare (trycloudflare.com) para webhook Telegram sin cuenta."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Tuple

_TRYCLOUDFLARE_URL = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com/?", re.IGNORECASE
)


def cloudflared_available() -> bool:
    return shutil.which("cloudflared") is not None


def pm2_available() -> bool:
    return shutil.which("pm2") is not None


def sanitize_pm2_name(raw: str, *, suffix: str, max_len: int = 45) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", (raw or "").strip()) or "duckclaw"
    name = f"{base}-{suffix}"
    return name[:max_len].strip("-") or f"duckclaw-{suffix}"


def extract_last_trycloudflare_url(blob: str) -> str | None:
    matches = _TRYCLOUDFLARE_URL.findall(blob or "")
    if not matches:
        return None
    return matches[-1].rstrip("/")


def _pm2_delete(name: str) -> None:
    subprocess.run(
        ["pm2", "delete", name],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _start_cloudflared_via_pm2(
    cloudflared_bin: str,
    pm2_name: str,
    port: int,
) -> Tuple[str | None, str]:
    _pm2_delete(pm2_name)
    start = subprocess.run(
        [
            "pm2",
            "start",
            cloudflared_bin,
            "--name",
            pm2_name,
            "--",
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{port}",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if start.returncode != 0:
        err = (start.stderr or start.stdout or "").strip() or "pm2 start cloudflared falló"
        return None, err

    time.sleep(5.0)
    for _ in range(6):
        logs = subprocess.run(
            ["pm2", "logs", pm2_name, "--lines", "150", "--nostream"],
            capture_output=True,
            text=True,
            timeout=35,
        )
        blob = (logs.stdout or "") + (logs.stderr or "")
        url = extract_last_trycloudflare_url(blob)
        if url:
            return url, ""
        time.sleep(2.0)
    return None, (
        "cloudflared arrancó en PM2 pero no apareció *.trycloudflare.com en los logs recientes. "
        "Prueba: pm2 logs " + pm2_name
    )


def _start_cloudflared_foreground_orphan(
    cloudflared_bin: str,
    port: int,
    *,
    wait_seconds: float = 75.0,
) -> Tuple[str | None, str]:
    try:
        proc = subprocess.Popen(
            [
                cloudflared_bin,
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as e:
        return None, str(e)

    if not proc.stdout:
        return None, "cloudflared sin stdout"

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.08)
            continue
        url = extract_last_trycloudflare_url(line)
        if url:
            return url.rstrip("/"), ""
    try:
        proc.terminate()
    except Exception:
        pass
    return None, (
        "timeout esperando URL trycloudflare.com; instala PM2 o ejecuta a mano: "
        f"cloudflared tunnel --url http://127.0.0.1:{port}"
    )


def provision_trycloudflare_quick_tunnel(
    port: int,
    *,
    gateway_pm2_name: str,
    use_pm2: bool,
) -> Tuple[str | None, str, str]:
    """
    Arranca Quick Tunnel hacia 127.0.0.1:port y devuelve la base HTTPS (sin path).

    Returns:
        (url_base o None, mensaje_error o \"\", pm2_process_name o \"\").
    """
    cf = shutil.which("cloudflared")
    if not cf:
        return None, "No está `cloudflared` en el PATH (brew install cloudflared).", ""

    pm2_name = sanitize_pm2_name(gateway_pm2_name, suffix="cloudflared")
    if use_pm2 and pm2_available():
        url, err = _start_cloudflared_via_pm2(cf, pm2_name, port)
        if url:
            return url.rstrip("/"), "", pm2_name
        # Si PM2 falla, intentar túnel en segundo plano sin PM2.

    url, err = _start_cloudflared_foreground_orphan(cf, port)
    if url:
        return url, "", ""
    return None, err, ""

