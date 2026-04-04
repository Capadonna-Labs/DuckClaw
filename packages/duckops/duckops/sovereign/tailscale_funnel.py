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


def funnel_status_proxied_local_ports(data: dict[str, Any]) -> set[int]:
    """
    Puertos locales (127.0.0.1 / localhost) a los que el estado JSON del Funnel enruta tráfico.

    Sirve para avisar si ``tailscale funnel --bg --yes <nuevo_puerto>`` va a **sustituir** el destino
    del hostname HTTPS *.ts.net (un bot puede seguir teniendo la misma URL en Telegram).
    """
    ports: set[int] = set()
    web = data.get("Web")
    if not isinstance(web, dict):
        return ports
    for _key, cfg in web.items():
        if not isinstance(cfg, dict):
            continue
        handlers = cfg.get("Handlers")
        if not isinstance(handlers, dict):
            continue
        for hcfg in handlers.values():
            if not isinstance(hcfg, dict):
                continue
            proxy = str(hcfg.get("Proxy") or "")
            for m in re.finditer(
                r"(?:127\.0\.0\.1|localhost):(\d+)", proxy, flags=re.IGNORECASE
            ):
                try:
                    ports.add(int(m.group(1)))
                except ValueError:
                    continue
    return ports


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
) -> tuple[str | None, str, str]:
    """
    Asegura `tailscale funnel --bg --yes <port>` y devuelve
    ``(base_https_url, error_message, warning_message)``.

    Si ya hay un mapping Funnel hacia ese puerto, reutiliza la URL sin relanzar el comando.

    ``warning_message`` (no vacío) indica que el Funnel **cambiará** de puerto local: la misma URL
    *.ts.net dejará de enrutar a los procesos que escuchaban el puerto anterior.
    """
    ts = shutil.which("tailscale")
    if not ts:
        return None, "No está `tailscale` en el PATH (instala Tailscale y vuelve a intentar).", ""

    target = int(port)
    prior = funnel_status_json()
    warn_switch = ""
    if prior:
        mapped = funnel_status_proxied_local_ports(prior)
        if mapped and target not in mapped:
            prev = ", ".join(str(p) for p in sorted(mapped))
            warn_switch = (
                "El Funnel HTTPS (*.ts.net) de este nodo enrutaba al puerto local "
                f"{prev}. Al continuar, Tailscale lo reorientará al puerto {target}. "
                "Cualquier bot de Telegram cuyo getWebhookInfo use la misma URL base "
                "empezará a entregar updates al gateway de ese puerto (no es un fallo de .env). "
                "Para varios bots: otro hostname/túnel por gateway, proxy con virtual hosts, "
                "o multiplexación (docs/COMANDOS.md §2.0 Modo B)."
            )
        existing = public_base_url_from_funnel_status(
            prior, expected_local_port=port
        )
        if existing:
            return existing.rstrip("/"), "", warn_switch

    try:
        proc = subprocess.run(
            [ts, "funnel", "--bg", "--yes", str(target)],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return None, "Timeout ejecutando `tailscale funnel --bg --yes`.", warn_switch
    except OSError as e:
        return None, f"No se pudo ejecutar tailscale: {e}", warn_switch

    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if proc.returncode != 0:
        hint = (proc.stderr or proc.stdout or "").strip() or f"código {proc.returncode}"
        return None, f"tailscale funnel falló: {hint}", warn_switch

    m = _FUNNEL_URL_IN_TEXT_RE.search(combined)
    if m:
        return f"https://{m.group(1)}".rstrip("/"), "", warn_switch

    for _ in range(poll_attempts):
        time.sleep(poll_delay_sec)
        st = funnel_status_json()
        if st:
            found = public_base_url_from_funnel_status(
                st, expected_local_port=port
            )
            if found:
                return found.rstrip("/"), "", warn_switch

    return None, (
        "Funnel parece activo pero no se leyó la URL. "
        "Comprueba: `tailscale funnel status` y políticas Funnel en el admin de Tailscale."
    ), warn_switch
