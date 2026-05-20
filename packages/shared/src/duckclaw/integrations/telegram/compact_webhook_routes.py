# packages/shared/src/duckclaw/integrations/telegram/compact_webhook_routes.py
"""
Rutas multiplex por path (``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` modo compacto).

Formato por entrada (coma-separado)::

  bot_name:bot_token:/api/v1/telegram/sufijo:worker_id:tenant_id:vault_env_var

``vault_env_var`` es el **nombre** de una variable en .env cuyo valor es la ruta DuckDB
(p. ej. ``DUCKCLAW_MY_VAULT_DB_PATH``). Opcional: omitir ``:vault_env_var`` si no forzar bóveda.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from duckclaw.gateway_db import resolve_env_duckdb_path

# Rutas .env antiguas (bot:token:/api/v1/telegram/sufijo sin :worker:tenant)
_LEGACY_BOT_DEFAULT_WORKER: dict[str, str] = {
    "finanz": "finanz",
    "siata": "siata_analyst",
    "jobhunter": "job_hunter",
    "quanttrader": "quant_trader",
    "pqrsd-assistant": "pqrsd_assistant",
}


def _legacy_default_tenant_id() -> str:
    return (os.environ.get("DUCKCLAW_TELEGRAM_LEGACY_DEFAULT_TENANT") or "default").strip() or "default"


def _infer_legacy_worker_id(bot_name: str) -> str:
    key = (bot_name or "").strip().lower()
    if key in _LEGACY_BOT_DEFAULT_WORKER:
        return _LEGACY_BOT_DEFAULT_WORKER[key]
    return key.replace("-", "_")


@dataclass(frozen=True)
class TelegramCompactWebhookRoute:
    """Una entrada del .env (compacto)."""

    bot_name: str
    bot_token: str
    webhook_path: str
    worker_id: str
    tenant_id: str
    vault_env_var: str = ""


@dataclass(frozen=True)
class TelegramPathWebhookBinding:
    """Resuelto para enrutar un POST al grafo (worker, tenant, token, bóveda)."""

    bot_name: str
    bot_token: str
    worker_id: str
    tenant_id: str
    forced_vault_db_path: str | None
    webhook_path: str


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
        path_and_tail = entry[idx + 1 :].strip()
        tail_m = re.match(
            r"^(/api/v1/telegram/[^:]+):([^:]+):([^:]+)(?::([^:]+))?$",
            path_and_tail,
        )
        legacy_m = None
        if not tail_m:
            legacy_m = re.match(r"^(/api/v1/telegram/[^:]+)$", path_and_tail)
        if not tail_m and not legacy_m:
            raise ValueError(
                f"Formato inválido tras ':/api/': {path_and_tail[:100]!r}. "
                "Use bot:token:/api/v1/telegram/ruta:worker_id:tenant_id[:VAULT_ENV_VAR]"
            )
        if tail_m:
            path = tail_m.group(1).strip()
            worker_id = tail_m.group(2).strip()
            tenant_id = tail_m.group(3).strip()
            vault_env_var = (tail_m.group(4) or "").strip()
        else:
            assert legacy_m is not None
            path = legacy_m.group(1).strip()
            worker_id = ""
            tenant_id = ""
            vault_env_var = ""

        prefix = entry[:idx]
        first = prefix.find(":")
        if first <= 0:
            raise ValueError(f"No se pudo separar bot_name:token en: {entry[:80]!r}")
        bot_name = prefix[:first].strip().lower()
        bot_token = prefix[first + 1 :].strip()
        if not bot_name or not bot_token:
            raise ValueError(f"bot_name o bot_token vacío en: {entry[:80]!r}")
        if not worker_id:
            worker_id = _infer_legacy_worker_id(bot_name)
        if not tenant_id:
            tenant_id = _legacy_default_tenant_id()
        if not worker_id or not tenant_id:
            raise ValueError(
                f"Falta worker_id:tenant_id en ruta compacta de {bot_name!r}. "
                "Formato: bot:token:/api/v1/telegram/ruta:worker:tenant[:VAULT_ENV_VAR]"
            )

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
                worker_id=worker_id,
                tenant_id=tenant_id,
                vault_env_var=vault_env_var,
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
    vault_envs: tuple[str, ...] = ()
    if route.vault_env_var:
        vault_envs = (route.vault_env_var.strip(),)
    vault = _resolve_vault_path_from_env(vault_envs)
    return TelegramPathWebhookBinding(
        bot_name=route.bot_name,
        bot_token=route.bot_token,
        worker_id=route.worker_id,
        tenant_id=route.tenant_id,
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


def serialize_compact_telegram_webhook_routes(routes: list[TelegramCompactWebhookRoute]) -> str:
    """Serializa al formato compacto del .env (coma-separado)."""
    parts: list[str] = []
    for route in routes:
        bot = (route.bot_name or "").strip().lower()
        token = (route.bot_token or "").strip()
        path = (route.webhook_path or "").strip()
        worker = (route.worker_id or "").strip()
        tenant = (route.tenant_id or "").strip()
        vault = (route.vault_env_var or "").strip()
        if not bot or not token or not path or not worker or not tenant:
            raise ValueError(
                "bot_name, bot_token, webhook_path, worker_id y tenant_id son obligatorios en cada ruta"
            )
        base = f"{bot}:{token}:{path}:{worker}:{tenant}"
        parts.append(f"{base}:{vault}" if vault else base)
    return ",".join(parts)


def known_compact_bot_names() -> tuple[str, ...]:
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    return tuple(r.bot_name for r in parse_compact_telegram_webhook_routes(raw))


def load_path_webhook_bindings_from_env() -> list[TelegramPathWebhookBinding]:
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    routes = parse_compact_telegram_webhook_routes(raw)
    return [compact_route_to_path_binding(r) for r in routes]
