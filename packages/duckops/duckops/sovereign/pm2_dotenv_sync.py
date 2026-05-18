"""Regenera api_gateways_pm2.json y ecosystem.api.config.cjs desde .env (sin secretos)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from duckclaw.env_secrets import strip_dotenv_owned_from_env, strip_secrets_from_env
from duckclaw.ops.manager import _load_merged_gateway_apps, save_gateway_cluster_config

from duckclaw.dotenv_immutable import root_dotenv_flat_env


def _gateway_port_from_pm2_json(repo_root: Path, app_name: str, *, fallback: int = 8282) -> int:
    """Puerto en ``api_gateways_pm2.json`` (uvicorn ``--port``)."""
    for app in _load_merged_gateway_apps(str(repo_root)):
        if isinstance(app, dict) and (app.get("name") or "").strip() == app_name:
            p = int(app.get("port") or 0)
            if p > 0:
                return p
    return fallback


def _gateway_port(repo_root: Path, app_name: str, *, fallback: int = 8000) -> int:
    """Puerto: ``DUCKCLAW_GATEWAY_PORT`` en ``.env``, luego JSON, luego fallback."""
    dot = root_dotenv_flat_env(repo_root)
    raw = (dot.get("DUCKCLAW_GATEWAY_PORT") or "").strip()
    if raw.isdigit():
        p = int(raw)
        if p > 0:
            return p
    return _gateway_port_from_pm2_json(repo_root, app_name, fallback=fallback)


def minimal_gateway_env(_repo_root: Path, app_name: str) -> dict[str, str]:
    """Solo metadatos PM2; secretos, rutas y puertos viven en .env."""
    return {"DUCKCLAW_PM2_PROCESS_NAME": app_name}


def sync_gateway_pm2_from_dotenv(
    repo_root: Path,
    *,
    single_gateway: bool = True,
) -> list[dict[str, Any]]:
    """
    Persiste gateways sin secretos ni duplicados de .env.
    Con ``single_gateway=True`` deja un solo bloque (nombre/puerto desde .env).
    """
    repo_root = repo_root.resolve()
    dot = root_dotenv_flat_env(repo_root)
    name = (dot.get("DUCKCLAW_PM2_PROCESS_NAME") or "DuckClaw-Gateway").strip() or "DuckClaw-Gateway"
    port = _gateway_port(repo_root, name)

    if single_gateway:
        env = strip_dotenv_owned_from_env(strip_secrets_from_env(minimal_gateway_env(repo_root, name)))
        apps: list[dict[str, Any]] = [
            {"name": name, "host": "0.0.0.0", "port": port, "env": env},
        ]
    else:
        apps = _load_merged_gateway_apps(str(repo_root))
        cleaned: list[dict[str, Any]] = []
        for app in apps:
            if not isinstance(app, dict):
                continue
            n = (app.get("name") or "").strip()
            if not n:
                continue
            raw_env = app.get("env") if isinstance(app.get("env"), dict) else {}
            base = minimal_gateway_env(repo_root, n)
            merged = {**base, **{str(k): str(v) for k, v in raw_env.items() if v is not None}}
            merged["DUCKCLAW_PM2_PROCESS_NAME"] = n
            app_env = strip_dotenv_owned_from_env(strip_secrets_from_env(merged))
            cleaned.append(
                {
                    "name": n,
                    "host": (app.get("host") or "0.0.0.0").strip() or "0.0.0.0",
                    "port": int(app.get("port") or port),
                    "env": app_env,
                }
            )
        apps = cleaned or [
            {
                "name": name,
                "host": "0.0.0.0",
                "port": port,
                "env": strip_dotenv_owned_from_env(
                    strip_secrets_from_env(minimal_gateway_env(repo_root, name))
                ),
            }
        ]

    save_gateway_cluster_config(str(repo_root), apps)
    return apps


def rerender_gateway_pm2_ecosystem(repo_root: Path) -> None:
    """Tras materializar: sanea JSON existente y regenera ecosystem.api.config.cjs."""
    sync_gateway_pm2_from_dotenv(repo_root, single_gateway=True)
