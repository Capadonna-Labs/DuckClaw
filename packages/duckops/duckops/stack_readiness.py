"""Detectar si el repo ya pasó por duckops init."""

from __future__ import annotations

import os
from pathlib import Path

from duckops.admin_bootstrap import admin_bootstrap_ready, is_admin_key_valid


def _load_dotenv(repo_root: Path) -> None:
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(repo_root / ".env")
    except ImportError:
        pass


def _flat_env(repo_root: Path) -> dict[str, str]:
    from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

    return merged_root_and_proposed_flat_env(repo_root)


def needs_wizard_init(repo_root: Path) -> bool:
    """
    True si falta configuración mínima (admin + multiplex PM2) para levantar el stack.
    """
    _load_dotenv(repo_root)
    env = _flat_env(repo_root)
    email = (env.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    password = (env.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    api_key = (env.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not admin_bootstrap_ready(email, password, api_key):
        return True
    pm2_cfg = repo_root / "config" / "api_gateways_pm2.json"
    if not pm2_cfg.is_file():
        return True
    try:
        import json

        data = json.loads(pm2_cfg.read_text(encoding="utf-8"))
        apps = data.get("apps") if isinstance(data, dict) else None
        if not apps:
            return True
    except (OSError, json.JSONDecodeError):
        return True
    return False


def admin_credentials_hint(repo_root: Path) -> tuple[str, str]:
    """Email y password para mostrar al usuario (sin imprimir la key)."""
    env = _flat_env(repo_root)
    return (
        (env.get("DUCKCLAW_ADMIN_EMAIL") or "admin@duckclaw.local").strip(),
        (env.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip(),
    )


def stack_env_ready(repo_root: Path) -> bool:
    _load_dotenv(repo_root)
    env = _flat_env(repo_root)
    return is_admin_key_valid(env.get("DUCKCLAW_ADMIN_API_KEY"))
