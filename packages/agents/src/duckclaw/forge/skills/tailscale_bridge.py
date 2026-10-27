"""
Tailscale Bridge — conectividad y descubrimiento en la red Mesh.

Spec: docs/architecture/GATEWAY_PROCESS_BOUNDARIES.md
Requiere: tailscale instalado en el sistema (curl -fsSL https://tailscale.com/install.sh | sh)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Optional


def _tailscale_available() -> bool:
    """True si tailscale está instalado y en PATH."""
    return shutil.which("tailscale") is not None


def _run_tailscale_status() -> str:
    """Ejecuta tailscale status --json o tailscale status. Retorna salida como str."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    try:
        result = subprocess.run(
            ["tailscale", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _parse_status_output(raw: str) -> tuple[str, list[str]]:
    """
    Parsea la salida de tailscale status. Retorna (ConnectionStatus, lista de peers).
    ConnectionStatus: "Active" o "Down".
    Peers: ["192.0.2.10 (hostname)", ...]
    """
    if not raw or not raw.strip():
        return "Down", []

    # Intentar JSON primero
    try:
        data = json.loads(raw)
        peers: list[str] = []
        status = "Down"

        # Self: estado local
        self_obj = data.get("Self") or {}
        if isinstance(self_obj, dict):
            exit_node = self_obj.get("ExitNode") or False
            online = self_obj.get("Online", True)
            if online and not exit_node:
                status = "Active"

        # Peer: nodos conectados
        peer_map = data.get("Peer") or {}
        if isinstance(peer_map, dict):
            for _pid, peer in peer_map.items():
                if isinstance(peer, dict):
                    hostname = peer.get("HostName") or peer.get("ComputedName") or "unknown"
                    addrs = peer.get("TailscaleIPs") or peer.get("TailscaleIP") or []
                    if isinstance(addrs, str):
                        addrs = [addrs]
                    ip = addrs[0] if addrs else ""
                    if ip:
                        peers.append(f"{ip} ({hostname})")

        return status, peers
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: parsear salida de texto plano "tailscale status"
    lines = raw.strip().splitlines()
    peers = []
    status = "Down"
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Formato típico: "192.0.2.10   hostname    user@   -"
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("100."):
            ip = parts[0]
            hostname = parts[1] if len(parts) > 1 else "unknown"
            peers.append(f"{ip} ({hostname})")
            status = "Active"
        elif "connected" in line.lower() or "online" in line.lower():
            status = "Active"

    return status, peers


def _tailscale_status_impl() -> str:
    """Implementación interna del tool. Retorna ConnectionStatus y peers."""
    raw = _run_tailscale_status()
    status, peers = _parse_status_output(raw)
    if peers:
        peers_str = ", ".join(peers[:10])
        if len(peers) > 10:
            peers_str += f" (+{len(peers) - 10} más)"
        return f"ConnectionStatus: {status} | Peers: {peers_str}"
    if status == "Down":
        return f"ConnectionStatus: Down | Error: tailscale no responde o no está conectado"
    return f"ConnectionStatus: {status}"


def _tailscale_status_tool(config: Optional[dict] = None) -> Optional[Any]:
    """
    Crea un StructuredTool para verificar el estado de la Tailnet.
    config: tailscale_enabled, service_mapping (opcional).
    """
    if not _tailscale_available():
        return None
    cfg = config or {}
    if cfg.get("tailscale_enabled") is False:
        return None

    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        lambda: _tailscale_status_impl(),
        name="tailscale_status",
        description="Verifica el estado de la red Tailscale Mesh. Retorna ConnectionStatus (Active/Down) y lista de peers conectados. Usa para diagnosticar conectividad entre nodos de la red (p. ej. Mac Mini y servidor).",
    )


_API_BASE = "https://api.tailscale.com/api/v2"   # fixed: the tool never calls a host the model or the user typed
_EXPIRY_WARN_DAYS = 14
_STALE_AFTER_S = 600   # a device not seen for 10 minutes counts as offline when the API does not say


def _parse_ts(value: Any) -> Any:
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def summarize_devices(devices: list[dict[str, Any]], *, now: Any = None, name_contains: str = "", only_problems: bool = False) -> dict[str, Any]:
    """Compact, key-free view of the tailnet devices: who is online, who needs an update, whose key is about to expire."""
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for d in devices:
        if not isinstance(d, dict):
            continue
        name = str(d.get("hostname") or str(d.get("name") or "").split(".")[0] or "?")
        seen = _parse_ts(d.get("lastSeen"))
        online = d.get("connectedToControl")
        if online is None:
            online = bool(seen and (now - seen).total_seconds() <= _STALE_AFTER_S)
        expires = _parse_ts(d.get("expires"))
        expiry_off = bool(d.get("keyExpiryDisabled"))
        days_left = None if expiry_off or expires is None else (expires - now).days
        problems = []
        if not online:
            problems.append("sin conexión")
        if d.get("updateAvailable"):
            problems.append("actualización disponible")
        if days_left is not None and days_left <= _EXPIRY_WARN_DAYS:
            problems.append("clave vencida" if days_left < 0 else f"clave vence en {days_left} d")
        if d.get("authorized") is False:
            problems.append("sin autorizar")
        rows.append({
            "dispositivo": name, "so": d.get("os") or "", "ip": (d.get("addresses") or [""])[0], "en_linea": bool(online),
            "visto": seen.strftime("%Y-%m-%d %H:%M UTC") if seen else "", "version": d.get("clientVersion") or "",
            "etiquetas": d.get("tags") or [], "problemas": problems,
        })
    total = len(rows)
    needle = name_contains.strip().lower()
    if needle:
        rows = [r for r in rows if needle in r["dispositivo"].lower()]
    if only_problems:
        rows = [r for r in rows if r["problemas"]]
    return {"total": total, "en_linea": sum(1 for r in rows if r["en_linea"]), "mostrados": len(rows), "dispositivos": rows[:60]}


def _fetch_tailnet_devices(api_key: str, tailnet: str, *, timeout: float = 15.0) -> list[dict[str, Any]]:
    import urllib.error
    import urllib.parse
    import urllib.request

    req = urllib.request.Request(
        f"{_API_BASE}/tailnet/{urllib.parse.quote(tailnet, safe='')}/devices?fields=default",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 fixed https host
        return list((json.loads(resp.read().decode("utf-8")) or {}).get("devices") or [])


def _tailscale_devices_impl(db: Any, tenant_id: str, name_contains: str = "", only_problems: bool = False, *, fetch: Any = None) -> str:
    """Tool body. The key comes from Integraciones for the tenant, is never returned, and an error message never carries it."""
    import urllib.error

    from duckclaw.integration_secrets import resolve_integration_api_key

    api_key = resolve_integration_api_key("tailscale_api_key", db=db, tenant_id=tenant_id)
    tailnet = resolve_integration_api_key("tailscale_tailnet", db=db, tenant_id=tenant_id)
    if not api_key or not tailnet:
        return "Tailscale no está configurado: faltan la API key y el nombre de la tailnet en Integraciones → Infraestructura."
    try:
        devices = (fetch or _fetch_tailnet_devices)(api_key, tailnet)
    except urllib.error.HTTPError as exc:
        hint = {401: "la API key es inválida o venció", 403: "la API key no tiene permiso sobre esa tailnet", 404: "el nombre de la tailnet no existe"}.get(exc.code, "error de la API")
        return f"Tailscale respondió {exc.code}: {hint}."
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo consultar la API de Tailscale ({type(exc).__name__})."
    return json.dumps(summarize_devices(devices, name_contains=name_contains, only_problems=only_problems), ensure_ascii=False)


def _tailscale_devices_tool(config: Optional[dict], *, db: Any = None, tenant_id: str = "default") -> Optional[Any]:
    """Read-only tool over the official API; only offered when this tenant has stored the key and the tailnet name."""
    if db is None or (config or {}).get("tailscale_enabled") is False:
        return None
    from duckclaw.integration_secrets import resolve_integration_api_key

    if not (resolve_integration_api_key("tailscale_api_key", db=db, tenant_id=tenant_id) and resolve_integration_api_key("tailscale_tailnet", db=db, tenant_id=tenant_id)):
        return None
    from langchain_core.tools import StructuredTool

    def _run(name_contains: str = "", only_problems: bool = False) -> str:
        return _tailscale_devices_impl(db, tenant_id, name_contains, only_problems)

    return StructuredTool.from_function(
        _run,
        name="tailscale_devices",
        description=(
            "Estado de todos los dispositivos de la tailnet vía la API oficial de Tailscale (solo lectura): en línea o no, última vez visto, "
            "versión, si hay actualización o la clave vence pronto. only_problems=true deja solo los que necesitan atención; "
            "name_contains filtra por nombre. A diferencia de tailscale_status (CLI de este nodo), ve toda la red."
        ),
    )


def register_tailscale_skill(
    tools_list: list[Any],
    tailscale_config: Optional[dict] = None,
    *,
    db: Any = None,
    tenant_id: str = "default",
) -> None:
    """
    Registra tailscale_status (CLI local) y, si el tenant guardó la clave en Integraciones, tailscale_devices (API oficial).
    Llamar desde build_worker_graph o build_general_graph cuando el manifest tiene skills.tailscale.
    """
    if not tailscale_config:
        return
    try:
        tool = _tailscale_status_tool(tailscale_config)
        if tool:
            tools_list.append(tool)
    except Exception:
        pass
    try:
        api_tool = _tailscale_devices_tool(tailscale_config, db=db, tenant_id=tenant_id)
        if api_tool:
            tools_list.append(api_tool)
    except Exception:
        pass
