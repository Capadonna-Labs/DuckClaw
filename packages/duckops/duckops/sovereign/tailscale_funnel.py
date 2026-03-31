"""Tailscale Funnel: HTTPS público (*.ts.net) hacia el API Gateway local."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from typing import Any

_FUNNEL_URL_IN_TEXT_RE = re.compile(
    r"https://([a-zA-Z0-9][a-zA-Z0-9.-]*\.ts\.net)\b", re.IGNORECASE
)


def tailscale_cli_available() -> bool:
    return shutil.which("tailscale") is not None


def funnel_status_json() -> dict[str, Any] | None:
    ts = shutil.which("tailscale")
    if not ts:
        return None
    try:
        proc = subprocess.run(
            [ts, "funnel", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def public_base_url_from_funnel_status(
    data: dict[str, Any],
    *,
    expected_local_port: int,
) -> str | None:
    """
    Devuelve https://nodo...ts.net si AllowFunnel está activo y el proxy apunta al puerto local dado.
    """
    web = data.get("Web")
    if not isinstance(web, dict):
        return None
    allow = data.get("AllowFunnel")
    if not isinstance(allow, dict):
        allow = {}
    port = int(expected_local_port)
    needle_h = f"127.0.0.1:{port}"
    needle_l = f"localhost:{port}"
    for key, cfg in web.items():
        if not isinstance(key, str) or not allow.get(key):
            continue
        host = key.rsplit(":", 1)[0] if ":" in key else key
        base = f"https://{host}".rstrip("/")
        if not isinstance(cfg, dict):
            continue
        handlers = cfg.get("Handlers")
        if not isinstance(handlers, dict):
            continue
        for hcfg in handlers.values():
            if not isinstance(hcfg, dict):
                continue
            proxy = str(hcfg.get("Proxy") or "")
            if needle_h in proxy or needle_l in proxy:
                return base
    return None


def provision_tailscale_funnel_bg(
    port: int,
    *,
    poll_attempts: int = 10,
    poll_delay_sec: float = 0.45,
) -> tuple[str | None, str]:
    """
    Asegura `tailscale funnel --bg --yes <port>` y devuelve la base HTTPS pública (sin / final).
    Si ya hay un mapping Funnel hacia ese puerto, reutiliza la URL sin relanzar el comando.
    """
    ts = shutil.which("tailscale")
    if not ts:
        return None, "No está `tailscale` en el PATH (instala Tailscale y vuelve a intentar)."

    prior = funnel_status_json()
    if prior:
        existing = public_base_url_from_funnel_status(
            prior, expected_local_port=port
        )
        if existing:
            return existing.rstrip("/"), ""

    try:
        proc = subprocess.run(
            [ts, "funnel", "--bg", "--yes", str(int(port))],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return None, "Timeout ejecutando `tailscale funnel --bg --yes`."
    except OSError as e:
        return None, f"No se pudo ejecutar tailscale: {e}"

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if proc.returncode != 0:
        hint = (proc.stderr or proc.stdout or "").strip() or f"código {proc.returncode}"
        return None, f"tailscale funnel falló: {hint}"

    m = _FUNNEL_URL_IN_TEXT_RE.search(combined)
    if m:
        return f"https://{m.group(1)}".rstrip("/"), ""

    for _ in range(poll_attempts):
        time.sleep(poll_delay_sec)
        st = funnel_status_json()
        if st:
            found = public_base_url_from_funnel_status(
                st, expected_local_port=port
            )
            if found:
                return found.rstrip("/"), ""

    return None, (
        "Funnel parece activo pero no se leyó la URL. "
        "Comprueba: `tailscale funnel status` y políticas Funnel en el admin de Tailscale."
    )
