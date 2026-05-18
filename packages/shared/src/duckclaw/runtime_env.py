"""
Variables de runtime desde .env (fuente de verdad).

Orden típico: ``os.environ`` (PM2/uvicorn ya cargó ``.env``) →
``.env`` raíz + ``config/dotenv_wizard_proposed.env`` → fallback documentado.
"""

from __future__ import annotations

import os
from pathlib import Path

from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env
from duckclaw.gateway_port import (
    DEFAULT_GATEWAY_PORT,
    gateway_base_url,
    gateway_port_from_dotenv,
    resolve_gateway_port,
)

# Último recurso si no hay .env (debe existir en .env.example).
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _repo_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root or Path.cwd()).resolve()


def _flat(repo_root: Path | str | None) -> dict[str, str]:
    return merged_root_and_proposed_flat_env(_repo_root(repo_root))


def _use_process_env(repo_root: Path) -> bool:
    try:
        return repo_root.resolve() == Path.cwd().resolve()
    except OSError:
        return False


def resolve_redis_url(repo_root: Path | str | None = None) -> str:
    """``REDIS_URL`` o ``DUCKCLAW_REDIS_URL`` desde entorno / .env."""
    root = _repo_root(repo_root)
    if _use_process_env(root):
        for key in ("REDIS_URL", "DUCKCLAW_REDIS_URL"):
            val = (os.environ.get(key) or "").strip()
            if val:
                return val
    flat = _flat(repo_root)
    for key in ("REDIS_URL", "DUCKCLAW_REDIS_URL"):
        val = (flat.get(key) or "").strip()
        if val:
            return val
    return DEFAULT_REDIS_URL


def resolve_gateway_http_base(repo_root: Path | str | None = None) -> str:
    """Base URL del API Gateway (sin barra final)."""
    return gateway_base_url(repo_root)


def resolve_agent_chat_url(repo_root: Path | str | None = None) -> str:
    """URL completa ``POST /api/v1/agent/chat`` (heartbeat, scripts)."""
    root = _repo_root(repo_root)
    if _use_process_env(root):
        legacy = (os.environ.get("GATEWAY_URL") or "").strip()
        if legacy:
            return legacy
    return f"{resolve_gateway_http_base(repo_root)}/api/v1/agent/chat"


def resolve_api_base_url(repo_root: Path | str | None = None) -> str:
    """Base para rutas REST del gateway (quotes, subagents, etc.)."""
    root = _repo_root(repo_root)
    if _use_process_env(root):
        for key in ("DUCKCLAW_API_BASE_URL", "DUCKCLAW_GATEWAY_URL"):
            val = (os.environ.get(key) or "").strip().rstrip("/")
            if val:
                return val
    flat = _flat(repo_root)
    for key in ("DUCKCLAW_API_BASE_URL", "DUCKCLAW_GATEWAY_URL"):
        val = (flat.get(key) or "").strip().rstrip("/")
        if val:
            return val
    return resolve_gateway_http_base(repo_root)
