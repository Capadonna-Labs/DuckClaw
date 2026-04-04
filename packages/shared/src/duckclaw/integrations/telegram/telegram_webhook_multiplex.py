# packages/shared/src/duckclaw/integrations/telegram/telegram_webhook_multiplex.py
"""Multiplexación de un solo URL de webhook para varios bots (secret_token → worker + token)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from duckclaw.integrations.telegram.telegram_webhook_secret_header import (
    telegram_webhook_secret_expected_from_env,
)

_log = logging.getLogger(__name__)

_ENV_ROUTES = "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"


def _resolve_vault_db_path_for_multiplex(raw: str) -> str | None:
    """Ruta DuckDB absoluta para forzar la bóveda por bot (multiplex en un solo proceso)."""
    pth = (raw or "").strip()
    if not pth:
        return None
    path = Path(pth)
    if not path.is_absolute():
        root = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
        if root:
            path = (Path(root) / path).resolve()
        else:
            path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return str(path)


@dataclass(frozen=True)
class TelegramWebhookRouteBinding:
    secret: str
    worker_id: str
    tenant_id: str
    bot_token_env: str
    vault_db_env: str


@dataclass(frozen=True)
class TelegramWebhookResolvedDispatch:
    worker_id: str
    tenant_id: str
    bot_token: str
    forced_vault_db_path: str | None = None


def _parse_route_bindings(raw: str) -> list[TelegramWebhookRouteBinding]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise TypeError("JSON debe ser una lista")
    out: list[TelegramWebhookRouteBinding] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise TypeError(f"ruta[{i}] debe ser un objeto")
        d: dict[str, Any] = item
        secret = str(d.get("secret") or "").strip()
        worker_id = str(d.get("worker_id") or "").strip()
        bot_token_env = str(d.get("bot_token_env") or "").strip()
        vault_db_env = str(d.get("vault_db_env") or "").strip()
        tenant_id = str(d.get("tenant_id") or "default").strip() or "default"
        if not secret or not worker_id or not bot_token_env:
            raise ValueError(f"ruta[{i}]: secret, worker_id y bot_token_env son obligatorios")
        out.append(
            TelegramWebhookRouteBinding(
                secret=secret,
                worker_id=worker_id,
                tenant_id=tenant_id,
                bot_token_env=bot_token_env,
                vault_db_env=vault_db_env,
            )
        )
    return out


_cached_bindings: list[TelegramWebhookRouteBinding] | None = None
_cached_bindings_error: str | None = None


def telegram_webhook_route_bindings() -> tuple[list[TelegramWebhookRouteBinding], str | None]:
    """
    Cachea el parseo de DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES.
    Retorna (lista, error_parseo); si error_parseo no es None, la lista puede estar vacía.
    """
    global _cached_bindings, _cached_bindings_error
    if _cached_bindings is not None:
        return _cached_bindings, _cached_bindings_error

    raw = (os.environ.get(_ENV_ROUTES) or "").strip()
    if not raw:
        _cached_bindings = []
        _cached_bindings_error = None
        return _cached_bindings, _cached_bindings_error
    if not raw.startswith("["):
        # Modo compacto por path (DUCKCLAW): ver ``telegram_compact_webhook_routes`` en api-gateway.
        _cached_bindings = []
        _cached_bindings_error = None
        return _cached_bindings, _cached_bindings_error

    try:
        _cached_bindings = _parse_route_bindings(raw)
        _cached_bindings_error = None
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _log.warning("telegram webhook multiplex: %s inválido: %s", _ENV_ROUTES, exc)
        _cached_bindings = []
        _cached_bindings_error = str(exc)
    return _cached_bindings, _cached_bindings_error


def telegram_webhook_header_fingerprint(header_value: str | None) -> str:
    """Identificador corto para dedupe (distinto por bot / secreto)."""
    h = (header_value or "").strip().encode("utf-8")
    return hashlib.sha256(h).hexdigest()[:16] if h else "no_secret"


def telegram_webhook_resolve_dispatch(
    header_value: str | None,
    *,
    default_worker_id: str,
    default_tenant_id: str,
    default_bot_token: str,
) -> (
    Literal["reject"]
    | TelegramWebhookResolvedDispatch
    | tuple[Literal["legacy_default"], str, str, str]
):
    """
    Resuelve worker, tenant y token de salida.

    Retorna:
    - ``reject``: 403
    - ``TelegramWebhookResolvedDispatch``: ruta multiplex explícita
    - ``("legacy_default", worker, tenant, token)``: cabecera coincide con
      TELEGRAM_WEBHOOK_SECRET o no hay rutas y el modo clásico aplica
    """
    bindings, _parse_err = telegram_webhook_route_bindings()

    legacy = telegram_webhook_secret_expected_from_env()
    hdr = (header_value or "").strip()

    if not bindings:
        if not legacy:
            return (
                "legacy_default",
                default_worker_id,
                default_tenant_id,
                default_bot_token,
            )
        if not hdr:
            return "reject"
        if secrets.compare_digest(hdr, legacy):
            return (
                "legacy_default",
                default_worker_id,
                default_tenant_id,
                default_bot_token,
            )
        return "reject"

    # Multiplex: una cabecera debe coincidir con una ruta o con legacy.
    if hdr:
        for b in bindings:
            if secrets.compare_digest(hdr, b.secret):
                tok = (os.environ.get(b.bot_token_env) or "").strip()
                if not tok:
                    _log.error(
                        "telegram webhook multiplex: %s vacío para worker=%s",
                        b.bot_token_env,
                        b.worker_id,
                    )
                    return "reject"
                fv: str | None = None
                if b.vault_db_env:
                    fv = _resolve_vault_db_path_for_multiplex(
                        os.environ.get(b.vault_db_env) or ""
                    )
                return TelegramWebhookResolvedDispatch(
                    worker_id=b.worker_id,
                    tenant_id=b.tenant_id,
                    bot_token=tok,
                    forced_vault_db_path=fv,
                )
        if legacy and secrets.compare_digest(hdr, legacy):
            return (
                "legacy_default",
                default_worker_id,
                default_tenant_id,
                default_bot_token,
            )

    return "reject"
