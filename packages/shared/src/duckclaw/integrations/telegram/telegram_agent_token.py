# packages/shared/src/duckclaw/integrations/telegram/telegram_agent_token.py
"""
Convención .env: ``TELEGRAM_<ID_AGENT>_TOKEN`` donde ``ID_AGENT`` es el ``id`` del worker
(manifest), en mayúsculas y guiones como subrayado (p. ej. ``my-worker`` → ``TELEGRAM_MY_WORKER_TOKEN``).
"""

from __future__ import annotations

import os

__all__ = [
    "pm2_app_to_worker_map_from_env",
    "canonical_manifest_worker_id",
    "resolve_telegram_token_from_flat_env",
    "telegram_agent_token_env_name",
    "resolve_telegram_token_for_worker_id",
    "telegram_token_from_pm2_env_dict",
    "telegram_worker_ids_match_for_compact_route",
]


def pm2_app_to_worker_map_from_env() -> dict[str, str]:
    """
    Mapa PM2 app name → worker id desde ``DUCKCLAW_PM2_APP_WORKER_MAP``.

    Formato: ``My-Gateway=worker_a,Otro-Gateway=worker_b``
    """
    raw = (os.environ.get("DUCKCLAW_PM2_APP_WORKER_MAP") or "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        app, _, wid = part.partition("=")
        app = app.strip()
        wid = wid.strip()
        if app and wid:
            out[app] = wid
    return out


def canonical_manifest_worker_id(raw: str) -> str:
    """Normaliza guiones/espacios al id de carpeta (sin alias de producto en código)."""
    s = (raw or "").strip()
    if not s:
        return ""
    return s.replace("-", "_") if s.islower() else s


def telegram_worker_ids_match_for_compact_route(a: str, b: str) -> bool:
    """True si dos identificadores se refieren al mismo worker (case / guiones)."""
    xa = canonical_manifest_worker_id(a).lower().replace("_", "").replace("-", "")
    xb = canonical_manifest_worker_id(b).lower().replace("_", "").replace("-", "")
    return bool(xa and xa == xb)


def telegram_agent_token_env_name(worker_id: str) -> str:
    """Nombre estándar de variable: TELEGRAM_<ID>_TOKEN."""
    norm = canonical_manifest_worker_id(worker_id)
    if not norm:
        return ""
    safe = norm.replace("-", "_").upper()
    return f"TELEGRAM_{safe}_TOKEN"


def resolve_telegram_token_from_flat_env(env_flat: dict[str, str], worker_id: str) -> str:
    """Token Bot API para un worker leyendo un dict plano (p. ej. .env parseado)."""
    flat = {str(k).strip(): str(v).strip() for k, v in env_flat.items() if k}
    wid = canonical_manifest_worker_id(worker_id)
    if not wid:
        return flat.get("TELEGRAM_BOT_TOKEN", "").strip()
    primary = telegram_agent_token_env_name(wid)
    if primary:
        t = flat.get(primary, "").strip()
        if t:
            return t
    return flat.get("TELEGRAM_BOT_TOKEN", "").strip()


def resolve_telegram_token_for_worker_id(worker_id: str) -> str:
    """Resuelve token: ``TELEGRAM_<ID>_TOKEN`` → ``TELEGRAM_BOT_TOKEN``."""
    return resolve_telegram_token_from_flat_env(dict(os.environ), worker_id)


def telegram_token_from_pm2_env_dict(env: dict[str, object], worker_id: str) -> str:
    """Token en el bloque ``env`` de un proceso PM2."""
    if not isinstance(env, dict):
        return ""
    flat = {str(k): str(v).strip() if v is not None else "" for k, v in env.items()}
    wid = canonical_manifest_worker_id(worker_id)
    if wid:
        std = telegram_agent_token_env_name(wid)
        if std:
            t = flat.get(std, "").strip()
            if t:
                return t
    return flat.get("TELEGRAM_BOT_TOKEN", "").strip()
