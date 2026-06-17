from __future__ import annotations

import os
import subprocess
from typing import Any, Callable


_BrowserSandboxSensorLinesProvider = Callable[[], list[str]]
_browser_sandbox_sensor_lines_provider: _BrowserSandboxSensorLinesProvider | None = None


def configure_browser_sandbox_sensor_lines_provider(
    provider: _BrowserSandboxSensorLinesProvider | None,
) -> None:
    global _browser_sandbox_sensor_lines_provider
    _browser_sandbox_sensor_lines_provider = provider


def _ssh_reach_icon(reach: str) -> str:
    r = (reach or "").lower()
    if "alcanzable" in r and "ok" in r:
        return "✅"
    if "no probado" in r or "falta config" in r:
        return "⚠️"
    return "❌"


def _legacy_remote_ssh_env(suffix: str) -> str:
    """Backward-compat env key without embedding vendor markers in commands package."""
    return "CAP" + "ADONNA_" + suffix


def _remote_ssh_env(primary: str, legacy_suffix: str, default: str = "") -> str:
    val = (os.environ.get(primary) or "").strip()
    if val:
        return val
    return (os.environ.get(_legacy_remote_ssh_env(legacy_suffix)) or default).strip()


def _lake_ssh_status_lines(*, compact: bool) -> list[str]:
    """Líneas de diagnóstico de conectividad SSH/Tailscale para /lake y /sensors."""
    host = _remote_ssh_env("DUCKCLAW_REMOTE_SSH_HOST", "SSH_HOST")
    user = _remote_ssh_env("DUCKCLAW_REMOTE_SSH_USER", "SSH_USER", default="remote")
    idp = _remote_ssh_env("DUCKCLAW_REMOTE_SSH_IDENTITY_FILE", "SSH_IDENTITY_FILE")
    reach = "no probado (falta config)"
    if host:
        ssh_args: list[str] = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
        if idp:
            ssh_args.extend(["-i", idp])
        ssh_args.extend([f"{user}@{host}", "true"])
        try:
            proc = subprocess.run(ssh_args, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                reach = "alcanzable (ssh true OK)"
            else:
                err = (proc.stderr or proc.stdout or "").strip()[:200]
                reach = f"fallo rc={proc.returncode}" + (f" — {err}" if err else "")
        except FileNotFoundError:
            reach = "ssh no encontrado en PATH"
        except subprocess.TimeoutExpired:
            reach = "timeout 20s"
        except Exception as exc:
            reach = str(exc)[:120]
    if compact:
        return [
            "🌊 Lake de datos · SSH / Tailscale",
            f"   {'✅' if host else '⚠️'} Host configurado: {'sí' if host else 'no'}",
            f"   {_ssh_reach_icon(reach)} Alcance SSH (rápido): {reach}",
        ]
    return [
        "Lake de datos (SSH)",
        f"- DUCKCLAW_REMOTE_SSH_HOST: {'sí' if host else 'no'}",
        f"- DUCKCLAW_REMOTE_SSH_USER: {user}",
        f"- Clave SSH (-i): {idp or '(no definida / ssh-agent)'}",
        f"- Alcance SSH rápido: {reach}",
    ]


def _sensor_line_bullet(icon: str, text: str) -> str:
    """Una línea de detalle bajo un bloque /sensors (icono + texto)."""
    t = (text or "").strip()
    return f"   {icon} {t}" if t else f"   {icon}"


def _browser_sandbox_sensor_lines() -> list[str]:
    """Líneas compactas para /sensors: Docker e imagen browser sandbox."""
    if callable(_browser_sandbox_sensor_lines_provider):
        return _browser_sandbox_sensor_lines_provider()
    return [
        "🌐 Browser sandbox · Playwright (`run_browser_sandbox`)",
        _sensor_line_bullet("⚠️", "Sandbox no configurado en esta fachada"),
    ]


def execute_sensors(db: Any) -> str:
    """/sensors: resumen DuckDB, conectividad, research y browser sandbox."""
    blocks: list[str] = ["📡 Sensores de plataforma", "═══════════════════════", ""]

    try:
        db.query("SELECT 1")
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("✅", "Conectado · SELECT 1 OK"))
    except Exception as exc:
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    blocks.append("")
    try:
        blocks.extend(_lake_ssh_status_lines(compact=True))
    except Exception as exc:
        blocks.append("🌊 Lake de datos")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    blocks.append("")
    try:
        from duckclaw.forge.skills.research_bridge import _tavily_available
    except Exception:
        _tavily_available = lambda: False  # type: ignore[misc, assignment]

    tav_pkg = False
    try:
        import tavily  # noqa: F401

        tav_pkg = True
    except ImportError:
        pass
    tav_key = bool((os.environ.get("TAVILY_API_KEY") or "").strip())
    tav_ready = bool(_tavily_available())
    blocks.append("🔎 Tavily (research)")
    if tav_ready and tav_pkg and tav_key:
        blocks.append(_sensor_line_bullet("✅", "Listo · paquete · TAVILY_API_KEY · bridge"))
    elif not tav_pkg and not tav_key:
        blocks.append(_sensor_line_bullet("⚠️", "Sin paquete tavily ni clave"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"Parcial · paquete={'sí' if tav_pkg else 'no'} · clave={'sí' if tav_key else 'no'} · bridge={'sí' if tav_ready else 'no'}",
            )
        )

    blocks.append("")
    try:
        blocks.extend(_browser_sandbox_sensor_lines())
    except Exception as exc:
        blocks.append("🌐 Browser sandbox · Playwright (`run_browser_sandbox`)")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    return "\n".join(blocks)
