"""Carga .env y overrides PM2 por proceso gateway (DB paths, token Telegram)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from duckclaw.gateway_db import (
    GATEWAY_DB_ENV_KEYS,
    raw_gateway_db_path_from_mapping,
    resolve_env_duckdb_path,
)
from duckclaw.integrations.telegram.telegram_agent_token import (
    pm2_app_to_worker_map_from_env,
    resolve_telegram_token_for_worker_id,
    telegram_token_from_pm2_env_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def apply_dotenv_from_repo() -> None:
    """Carga .env desde repo root (fuente de verdad para secretos; PM2 env_file + override abajo)."""
    dotenv_flat: dict[str, str] = {}
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    for base in (_REPO_ROOT, Path.cwd()):
        env_path = base / ".env"
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                ks = key.strip()
                if not ks:
                    continue
                dotenv_flat[ks] = value.strip().strip("'\"")
        break
    if not dotenv_flat:
        return
    from duckclaw.env_secrets import DOTENV_OVERRIDE_KEYS, apply_dotenv_overrides_to_os_environ

    for ks, vs in dotenv_flat.items():
        if ks in DOTENV_OVERRIDE_KEYS:
            continue
        os.environ.setdefault(ks, vs)
    apply_dotenv_overrides_to_os_environ(dotenv_flat)


def apply_db_path_from_api_gateways_pm2() -> tuple[bool, str | None]:
    """
    Varias apps PM2 comparten el mismo .env. Volcar al proceso las claves ``DUCKCLAW_*_DB_PATH``
    y ``DUCKDB_PATH`` del bloque ``config/api_gateways_pm2.json`` según
    ``DUCKCLAW_PM2_PROCESS_NAME`` o ``--port`` (uvicorn).

    También aplica `TELEGRAM_BOT_TOKEN` desde ese mismo bloque `env` si viene definido y no vacío:
    así un gateway dedicado puede usar su bot aunque el .env global traiga otro token.
    Se ejecuta después de cargar .env, así este valor **sustituye** al de setdefault.

    Returns:
        (telegram_token_from_json, matched_app_name) — nombre PM2 del bloque elegido (p. ej.
        ``BI-Analyst-Gateway``), útil si ``DUCKCLAW_PM2_PROCESS_NAME`` no está en el entorno
        (uvicorn directo por puerto).
    """
    cfg = _REPO_ROOT / "config" / "api_gateways_pm2.json"
    if not cfg.is_file():
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None
    try:
        raw = json.loads(cfg.read_text(encoding="utf-8"))
        apps = raw.get("apps") if isinstance(raw, dict) else None
        if not isinstance(apps, list):
            os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
            return False, None
    except Exception:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None

    proc_name = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    chosen: dict | None = None
    if proc_name:
        for app_entry in apps:
            if isinstance(app_entry, dict) and (app_entry.get("name") or "").strip() == proc_name:
                chosen = app_entry
                break
    if chosen is None:
        port: int | None = None
        try:
            argv = sys.argv
            for i, x in enumerate(argv):
                if x == "--port" and i + 1 < len(argv):
                    port = int(argv[i + 1])
                    break
        except (ValueError, IndexError):
            port = None
        if port is not None:
            matches = [
                a for a in apps
                if isinstance(a, dict) and int(a.get("port") or 0) == port
            ]
            if len(matches) == 1:
                chosen = matches[0]
    if chosen is None:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None
    matched_name = (chosen.get("name") or "").strip() or None
    if matched_name:
        os.environ["DUCKCLAW_PM2_MATCHED_APP_NAME"] = matched_name
    else:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
    env = chosen.get("env") if isinstance(chosen.get("env"), dict) else {}
    for key in GATEWAY_DB_ENV_KEYS:
        raw_v = str(env.get(key) or "").strip()
        if raw_v:
            os.environ[key] = resolve_env_duckdb_path(raw_v)
    legacy = str(env.get("DUCKCLAW_DB_PATH") or "").strip()
    if legacy and not any(str(env.get(k) or "").strip() for k in GATEWAY_DB_ENV_KEYS):
        os.environ.setdefault("DUCKCLAW_GATEWAY_DB_PATH", resolve_env_duckdb_path(legacy))
    if not any(os.environ.get(k) for k in GATEWAY_DB_ENV_KEYS):
        dbp = raw_gateway_db_path_from_mapping(env)
        if dbp:
            os.environ["DUCKCLAW_GATEWAY_DB_PATH"] = resolve_env_duckdb_path(dbp)
    matched_app = (matched_name or "").strip()
    wid = pm2_app_to_worker_map_from_env().get(matched_app, "")
    tok = (
        telegram_token_from_pm2_env_dict(env, wid)
        if wid
        else (str(env.get("TELEGRAM_BOT_TOKEN") or "")).strip()
    )
    if tok:
        os.environ["TELEGRAM_BOT_TOKEN"] = tok
        return True, matched_name
    return False, matched_name


def apply_telegram_token_per_gateway_env(*, matched_pm2_app_name: str | None) -> None:
    """
    Si el bloque PM2 no fijó token: resuelve desde .env con
    ``TELEGRAM_<ID_AGENT>_TOKEN`` (estándar) o nombres legados.

    Ver: ``duckclaw.integrations.telegram.telegram_agent_token``.
    """
    proc = (
        (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
        or (matched_pm2_app_name or "").strip()
    )
    wid = pm2_app_to_worker_map_from_env().get(proc)
    if not wid:
        return
    alt = resolve_telegram_token_for_worker_id(wid)
    if alt:
        os.environ["TELEGRAM_BOT_TOKEN"] = alt


def apply_gateway_bootstrap() -> None:
    """Dotenv + overrides PM2 (DB paths y token Telegram por proceso)."""
    apply_dotenv_from_repo()
    telegram_token_from_pm2_json, matched_pm2_app_name = apply_db_path_from_api_gateways_pm2()
    if not telegram_token_from_pm2_json:
        apply_telegram_token_per_gateway_env(matched_pm2_app_name=matched_pm2_app_name)
