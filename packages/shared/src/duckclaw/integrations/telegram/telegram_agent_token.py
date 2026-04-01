# packages/shared/src/duckclaw/integrations/telegram/telegram_agent_token.py
"""
Convención .env: ``TELEGRAM_<ID_AGENT>_TOKEN`` donde ``ID_AGENT`` es el ``id`` del worker
(manifest), en mayúsculas y con guiones como subrayado (p. ej. ``bi_analyst`` → ``TELEGRAM_BI_ANALYST_TOKEN``).

Se mantienen lecturas fallback a los nombres legados (``TELEGRAM_BOT_TOKEN_BI_ANALYST``, etc.).
"""

from __future__ import annotations

import os

__all__ = [
    "PM2_GATEWAY_APP_TO_WORKER_ID",
    "canonical_manifest_worker_id",
    "resolve_telegram_token_from_flat_env",
    "telegram_agent_token_env_name",
    "resolve_telegram_token_for_worker_id",
    "telegram_token_from_pm2_env_dict",
]

# Nombre de app PM2 (p. ej. config/api_gateways_pm2.json) → id del worker en Forge.
PM2_GATEWAY_APP_TO_WORKER_ID: dict[str, str] = {
    "Finanz-Gateway": "finanz",
    "BI-Analyst-Gateway": "bi_analyst",
    "Leila-Gateway": "LeilaAssistant",
    "SIATA-Gateway": "siata_analyst",
}


def canonical_manifest_worker_id(raw: str) -> str:
    """Normaliza nombres tipo ``BI-Analyst`` o ``bi_analyst`` al ``id`` del manifest."""
    s = (raw or "").strip()
    if not s:
        return ""
    norm = s.replace("-", "_")
    low = norm.lower()
    if low == "bi_analyst":
        return "bi_analyst"
    if low == "finanz":
        return "finanz"
    if low == "siata_analyst":
        return "siata_analyst"
    if low == "leilaassistant" or s == "LeilaAssistant":
        return "LeilaAssistant"
    return norm


def telegram_agent_token_env_name(worker_id: str) -> str:
    """Nombre estándar de variable: TELEGRAM_<ID>_TOKEN."""
    norm = canonical_manifest_worker_id(worker_id)
    if not norm:
        return ""
    return f"TELEGRAM_{norm.upper()}_TOKEN"


# worker manifest id → nombres de env antiguos (solo lectura).
_LEGACY_ENV_BY_WORKER: dict[str, tuple[str, ...]] = {
    "bi_analyst": ("TELEGRAM_BOT_TOKEN_BI_ANALYST",),
    "LeilaAssistant": ("TELEGRAM_BOT_TOKEN_LEILA",),
    "siata_analyst": ("TELEGRAM_BOT_TOKEN_SIATA",),
}


def resolve_telegram_token_from_flat_env(env_flat: dict[str, str], worker_id: str) -> str:
    """Como ``resolve_telegram_token_for_worker_id`` pero leyendo un dict (p. ej. .env parseado)."""
    flat = {str(k).strip(): str(v).strip() for k, v in env_flat.items() if k}
    wid = canonical_manifest_worker_id(worker_id)
    if not wid:
        return flat.get("TELEGRAM_BOT_TOKEN", "").strip()
    primary = telegram_agent_token_env_name(wid)
    if primary:
        t = flat.get(primary, "").strip()
        if t:
            return t
    for leg in _LEGACY_ENV_BY_WORKER.get(wid, ()):
        t = flat.get(leg, "").strip()
        if t:
            return t
    if wid.lower() == "finanz":
        return flat.get("TELEGRAM_BOT_TOKEN", "").strip()
    return ""


def resolve_telegram_token_for_worker_id(worker_id: str) -> str:
    """
    Resuelve token Bot API para un worker por id de plantilla.

    Orden: ``TELEGRAM_<ID>_TOKEN`` → aliases legados por worker → para ``finanz``,
    ``TELEGRAM_BOT_TOKEN`` si no hubo valor previo.
    """
    return resolve_telegram_token_from_flat_env(dict(os.environ), worker_id)


def telegram_token_from_pm2_env_dict(env: dict[str, object], worker_id: str) -> str:
    """
    Token definido en el bloque ``env`` de un proceso PM2.

    Orden: ``TELEGRAM_BOT_TOKEN`` (compat) → ``TELEGRAM_<ID>_TOKEN`` → envs legados.
    """
    if not isinstance(env, dict):
        return ""
    flat = {str(k): str(v).strip() if v is not None else "" for k, v in env.items()}
    t = flat.get("TELEGRAM_BOT_TOKEN", "").strip()
    if t:
        return t
    wid = canonical_manifest_worker_id(worker_id)
    if not wid:
        return ""
    std = telegram_agent_token_env_name(wid)
    if std:
        t = flat.get(std, "").strip()
        if t:
            return t
    for leg in _LEGACY_ENV_BY_WORKER.get(wid, ()):
        t = flat.get(leg, "").strip()
        if t:
            return t
    return ""
