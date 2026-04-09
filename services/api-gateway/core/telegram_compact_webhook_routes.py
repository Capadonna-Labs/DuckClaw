# services/api-gateway/core/telegram_compact_webhook_routes.py
"""
Rutas multiplex por **path** (un túnel, varios bots).

Formato de ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` (modo compacto, distinto del JSON con ``secret``):

``bot_name:bot_token:webhook_path`` separado por comas. El token puede contener ``:``; el path comienza
con ``/api/`` y se detecta con ``rfind(":/api/")``.

Ejemplo::

    finanz:123456:AA...token:/api/v1/telegram/finanz,siata:789:BB...:/api/v1/telegram/siata
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from duckclaw.gateway_db import resolve_env_duckdb_path


@dataclass(frozen=True)
class TelegramCompactWebhookRoute:
    """Una entrada literal del .env (compacto)."""

    bot_name: str
    bot_token: str
    webhook_path: str


@dataclass(frozen=True)
class TelegramPathWebhookBinding:
    """Resuelto para enrutar un POST al grafo (worker, tenant, token, bóveda)."""

    bot_name: str
    bot_token: str
    worker_id: str
    tenant_id: str
    forced_vault_db_path: str | None
    webhook_path: str


# bot_name (minúsculas) → worker_id, tenant_id, variables de entorno para DuckDB (orden de preferencia)
_BOT_PROFILES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "finanz": ("finanz", "Finanzas", ("DUCKCLAW_FINANZ_DB_PATH",)),
    "siata": ("siata_analyst", "SIATA", ("DUCKCLAW_SIATA_DB_PATH",)),
    "jobhunter": ("Job-Hunter", "Trabajo", ("DUCKCLAW_JOB_HUNTER_DB_PATH",)),
    # Bóveda propia: DUCKCLAW_QUANT_TRADER_DB_PATH; fallback a finanz si no está definida.
    "quanttrader": (
        "quant_trader",
        "Finanzas",
        ("DUCKCLAW_QUANT_TRADER_DB_PATH", "DUCKCLAW_FINANZ_DB_PATH"),
    ),
}


def parse_compact_telegram_webhook_routes(raw: str) -> list[TelegramCompactWebhookRoute]:
    """
    Parsea el formato compacto. Si ``raw`` vacío, no compacto, o parece JSON multiplex (empieza por ``[``),
    devuelve lista vacía.
    """
    text = (raw or "").strip()
    if not text or text.startswith("["):
        return []
    if ":/api/" not in text:
        return []

    seen_paths: set[str] = set()
    seen_bots: set[str] = set()
    out: list[TelegramCompactWebhookRoute] = []

    for chunk in text.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        idx = entry.rfind(":/api/")
        if idx < 0:
            raise ValueError(
                f"DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES compacto: entrada sin ':/api/…': {entry[:80]!r}"
            )
        path = entry[idx + 1 :].strip()
        if not path.startswith("/api/"):
            raise ValueError(f"webhook_path inválido (debe empezar por /api/): {path!r}")
        prefix = entry[:idx]
        first = prefix.find(":")
        if first <= 0:
            raise ValueError(f"No se pudo separar bot_name:token en: {entry[:80]!r}")
        bot_name = prefix[:first].strip().lower()
        bot_token = prefix[first + 1 :].strip()
        if not bot_name or not bot_token:
            raise ValueError(f"bot_name o bot_token vacío en: {entry[:80]!r}")

        if path in seen_paths:
            raise ValueError(f"duplicate webhook_path: {path}")
        if bot_name in seen_bots:
            raise ValueError(f"duplicate bot_name: {bot_name}")
        seen_paths.add(path)
        seen_bots.add(bot_name)
        out.append(
            TelegramCompactWebhookRoute(
                bot_name=bot_name,
                bot_token=bot_token,
                webhook_path=path.rstrip("/") or path,
            )
        )

    return out


def _resolve_vault_path_from_env(env_names: tuple[str, ...]) -> str | None:
    for key in env_names:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        resolved = (resolve_env_duckdb_path(raw) or "").strip()
        if resolved:
            return resolved
    return None


def compact_route_to_path_binding(route: TelegramCompactWebhookRoute) -> TelegramPathWebhookBinding:
    profile = _BOT_PROFILES.get(route.bot_name)
    if not profile:
        known = ", ".join(sorted(_BOT_PROFILES))
        raise ValueError(
            f"bot_name desconocido {route.bot_name!r}; perfiles soportados: {known}"
        )
    worker_id, tenant_id, vault_envs = profile
    vault = _resolve_vault_path_from_env(vault_envs)
    return TelegramPathWebhookBinding(
        bot_name=route.bot_name,
        bot_token=route.bot_token,
        worker_id=worker_id,
        tenant_id=tenant_id,
        forced_vault_db_path=vault,
        webhook_path=route.webhook_path,
    )


def fastapi_relative_path(webhook_path: str, *, api_prefix: str = "/api/v1/telegram") -> str:
    """Sufijo para APIRouter(prefix=api_prefix): ``'/finanz'`` desde ``'/api/v1/telegram/finanz'``."""
    p = (webhook_path or "").strip().rstrip("/")
    pre = api_prefix.rstrip("/")
    if not p.startswith(pre + "/") and p != pre:
        raise ValueError(f"webhook_path debe estar bajo {api_prefix!r}, recibido: {webhook_path!r}")
    suffix = p[len(pre) :] or ""
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    if suffix == "/":
        raise ValueError("webhook_path no puede ser igual al prefix solo")
    return suffix


def load_path_webhook_bindings_from_env() -> list[TelegramPathWebhookBinding]:
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    routes = parse_compact_telegram_webhook_routes(raw)
    return [compact_route_to_path_binding(r) for r in routes]
