#!/usr/bin/env python3
"""DuckClaw Doctor — comprobaciones locales de diagnóstico (uv run python scripts/doctor.py)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_dotenv_repo() -> None:
    env_path = _repo_root() / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)


def _ok(msg: str) -> str:
    return f"✅ {msg}"


def _warn(msg: str) -> str:
    return f"⚠️  {msg}"


def _fail(msg: str) -> str:
    return f"❌ {msg}"


def check_1_repo_layout() -> str:
    root = _repo_root()
    if (root / "pyproject.toml").is_file():
        return _ok("Raíz del repo y pyproject.toml presentes.")
    return _fail("No se encontró pyproject.toml (ejecutar desde clone DuckClaw).")


def check_2_env_file() -> str:
    p = _repo_root() / ".env"
    if p.is_file():
        return _ok(f"Archivo .env presente ({p}).")
    return _warn("Sin .env en la raíz (copiar desde .env.example).")


def check_3_redis_url() -> str:
    raw = (os.environ.get("REDIS_URL") or "").strip()
    if not raw:
        return _warn("REDIS_URL vacío tras cargar .env (gateway necesita Redis en runtime).")
    return _ok("REDIS_URL definido.")


def check_4_redis_ping() -> str:
    raw = (os.environ.get("REDIS_URL") or "").strip()
    if not raw:
        return _warn("Redis: omitiendo ping (REDIS_URL vacío).")
    try:
        import redis
    except ImportError:
        return _warn("redis py no instalado en este interpreter; omitiendo ping.")
    try:
        r = redis.Redis.from_url(raw, decode_responses=True)
        if r.ping():
            return _ok("Redis PING OK.")
        return _fail("Redis PING devolvió falso.")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Redis no accesible: {exc}")


def check_5_gateway_db_path() -> str:
    try:
        sys.path.insert(0, str(_repo_root()))
        sys.path.insert(0, str(_repo_root() / "packages" / "shared" / "src"))
        from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path
    except Exception as exc:  # noqa: BLE001
        return _warn(f"No se importó duckclaw.gateway_db: {exc}")

    gp = str(get_gateway_db_path() or "").strip()
    if not gp:
        return _warn("gateway_db_path no resolvió (¿DUCKDB_PATH / multiplex en PM2?).")
    try:
        path = resolve_env_duckdb_path(gp)
        return _ok(f"Gateway DB configurada → {path}")
    except Exception as exc:  # noqa: BLE001
        return _warn(f"gateway_db_path con advertencia de resolución: {exc}")


def check_6_python_path() -> str:
    return _ok(f"Python {sys.version.split()[0]} ({sys.executable})")


def check_7_docker_cli() -> str:
    if not shutil.which("docker"):
        return _warn("CLI `docker` no está en PATH (GitHub MCP vía OrbStack necesita docker).")
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=18,
            check=False,
        )
        if r.returncode == 0:
            return _ok("`docker info` OK (daemon contactable).")
        return _warn("`docker info` falló (¿daemon Docker/OrbStack apagado?).")
    except FileNotFoundError:
        return _warn("`docker` no ejecutable.")
    except subprocess.TimeoutExpired:
        return _warn("`docker info` timeout.")


def check_8_mcp_pkg() -> str:
    try:
        import mcp  # noqa: F401
        return _ok("Paquete Python `mcp` importable.")
    except ImportError:
        return _warn("Paquete `mcp` no instalado (uv sync con extra agents/github según proyecto).")


def check_9_github_mcp() -> str:
    """
    GitHub MCP (Docker oficial):
    - GITHUB_TOKEN en entorno tras .env
    - imagen ghcr.io/github/github-mcp-server
    - llamada rápida a api.github.com/user si hay token
    """
    tok = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not tok:
        return (
            _warn(
                "GITHUB_TOKEN no configurado. GitHub MCP deshabilitado. "
                "Genera un PAT en https://github.com/settings/tokens "
                "con scopes: repo, read:org, read:user"
            )
        )

    image = (
        os.environ.get("DUCKCLAW_GITHUB_MCP_IMAGE", "ghcr.io/github/github-mcp-server").strip()
        or "ghcr.io/github/github-mcp-server"
    )
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return _warn(f"GitHub MCP: imagen Docker ausente `{image}` — Ejecuta: docker pull {image}")
    except FileNotFoundError:
        return _warn("docker CLI ausente — no se pudo validar imagen GitHub MCP.")
    except subprocess.TimeoutExpired:
        return _warn("`docker image inspect` timeout.")

    try:
        import httpx

        resp = httpx.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {tok}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15.0,
        )
        code = resp.status_code
    except Exception as exc:  # noqa: BLE001
        return _warn(f"GitHub MCP: error de red al probar PAT: {exc}")

    if code == 200:
        return _ok("GitHub MCP listo (imagen Docker + PAT válido ante api.github.com).")
    if code == 401:
        return _warn("GitHub MCP: PAT inválido o expirado (HTTP 401 en api.github.com/user).")
    return _warn(f"GitHub MCP: api.github.com/user → HTTP {code}")


def check_spawn_orphan_queue() -> str | None:
    """
    Perfil Spawn: hub RW inline, sin colas huérfanas.
    Retorna None si no aplica (no es perfil spawn).
    """
    try:
        sys.path.insert(0, str(_repo_root() / "packages" / "shared" / "src"))
        from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path
        from duckclaw.spawn_profile import is_spawn_profile, spawn_inline_writes_enabled
    except Exception as exc:  # noqa: BLE001
        return _warn(f"Spawn: no se importó spawn_profile: {exc}")

    if not is_spawn_profile():
        return None

    lines: list[str] = []
    if not spawn_inline_writes_enabled():
        lines.append("DUCKCLAW_SPAWN_USE_DB_WRITER=1: escrituras vía cola (necesitas PM2 DB-Writer).")
    else:
        lines.append("Escrituras inline activas (sin depender de duckdb_write_queue).")

    ro_flags = [
        k
        for k, v in os.environ.items()
        if "READ_ONLY" in k.upper() and str(v).strip().lower() in ("1", "true", "yes", "on")
    ]
    if ro_flags:
        lines.append(f"⚠️ Env fuerza solo lectura: {', '.join(sorted(ro_flags)[:8])}")

    if shutil.which("pm2"):
        try:
            proc = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if proc.returncode == 0 and "DuckClaw-DB-Writer" in (proc.stdout or ""):
                lines.append(
                    "PM2 tiene DuckClaw-DB-Writer (opcional; con inline spawn puede duplicar escritores)."
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    try:
        gp = resolve_env_duckdb_path(get_gateway_db_path())
        if Path(gp).is_file():
            lines.append(f"Hub DuckDB presente → {gp}")
        else:
            lines.append(f"⚠️ Hub DuckDB ausente (ejecutar bootstrap_dbs --core-only): {gp}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"⚠️ No se resolvió ruta hub: {exc}")

    return _ok("Spawn: " + " ".join(lines))


def check_10_openrouter() -> str:
    """OpenRouter API key + conectividad (app attribution headers)."""
    openrouter_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not openrouter_key:
        return (
            _warn(
                "OPENROUTER_API_KEY no configurado. "
                "OpenRouter disponible pero inactivo. Obtener en: openrouter.ai/keys"
            )
        )
    try:
        sys.path.insert(0, str(_repo_root() / "packages" / "shared" / "src"))
        from duckclaw.integrations.llm_providers import OPENROUTER_ATTRIBUTION_HEADERS
    except Exception as exc:  # noqa: BLE001
        return _warn(f"OpenRouter: no se importó llm_providers: {exc}")
    try:
        import httpx

        resp = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                **OPENROUTER_ATTRIBUTION_HEADERS,
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            models_count = len(resp.json().get("data", []))
            return (
                _ok(f"OpenRouter conectado. Modelos disponibles: {models_count}. "
                    f"App: openrouter.ai/apps?url=https://github.com/Capadonna-Labs/duckclaw")
            )
        return _fail(f"OpenRouter: HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"OpenRouter: {exc}")


_CHECKS = (
    ("1. Repo", check_1_repo_layout),
    ("2. .env", check_2_env_file),
    ("3. REDIS_URL", check_3_redis_url),
    ("4. Redis ping", check_4_redis_ping),
    ("5. Gateway DuckDB path", check_5_gateway_db_path),
    ("6. Python", check_6_python_path),
    ("7. Docker daemon", check_7_docker_cli),
    ("8. Paquete mcp", check_8_mcp_pkg),
    ("9. GitHub MCP", check_9_github_mcp),
    ("10. OpenRouter", check_10_openrouter),
)


def main() -> int:
    _load_dotenv_repo()
    print("DuckClaw Doctor — comprobaciones locales\n")
    for label, fn in _CHECKS:
        try:
            out = fn()
        except Exception as exc:  # noqa: BLE001
            out = _fail(f"{label}: excepción {exc}")
        print(f"{label}: {out}")
    try:
        spawn_out = check_spawn_orphan_queue()
        if spawn_out is not None:
            print(f"11. Spawn cola huérfana: {spawn_out}")
    except Exception as exc:  # noqa: BLE001
        print(f"11. Spawn cola huérfana: {_fail(f'excepción {exc}')}")
    print("\nDoctor finalizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
