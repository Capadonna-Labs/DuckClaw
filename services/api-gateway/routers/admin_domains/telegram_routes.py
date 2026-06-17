from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, admin_audit, mask_secret, problem, require_admin_key
from routers.admin_domains.env_config import read_env_key_unmasked

router = APIRouter(prefix="/telegram", tags=["admin-telegram-routes"])

_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY = "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
_TELEGRAM_WEBHOOK_ROUTES_DOMAIN = "telegram"
_TELEGRAM_WEBHOOK_ROUTES_KEY = "webhook_routes"


class TelegramRouteInput(BaseModel):
    bot: str = Field(..., min_length=1, max_length=64)
    path: str = Field(..., min_length=8, max_length=256)
    worker_id: str = Field(..., min_length=1, max_length=64)
    tenant_id: str = Field(..., min_length=1, max_length=64)
    vault_env_var: str | None = Field(
        default=None,
        max_length=128,
        description="Nombre de variable .env con ruta DuckDB (opcional)",
    )
    token: str | None = Field(
        default=None,
        max_length=512,
        description="Vacío = conservar token actual en .env",
    )


class TelegramRoutesPutBody(BaseModel):
    routes: list[TelegramRouteInput] = Field(default_factory=list)


def telegram_webhook_routes_runtime_setting() -> dict[str, Any]:
    """Rutas Telegram DB-first con fallback a `.env` bootstrap."""
    raw_env = (
        read_env_key_unmasked(_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY)
        or os.environ.get(_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY)
        or ""
    ).strip()
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        with open_gateway_db(read_only=True) as db:
            resolved = resolve_runtime_setting(
                db,
                tenant_id="global",
                actor_email="",
                domain=_TELEGRAM_WEBHOOK_ROUTES_DOMAIN,
                key=_TELEGRAM_WEBHOOK_ROUTES_KEY,
                env_key=_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY,
                default="",
            )
        return {
            "value": str(resolved.get("value") or raw_env or "").strip(),
            "source": str(resolved.get("source") or ("env" if raw_env else "default")),
        }
    except Exception:
        return {"value": raw_env, "source": "env" if raw_env else "default"}


def upsert_telegram_webhook_routes_runtime_setting(serialized: str, *, actor: str) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    command = UpsertRuntimeSettingCommand(
        tenant_id="global",
        actor_email="",
        domain=_TELEGRAM_WEBHOOK_ROUTES_DOMAIN,
        key=_TELEGRAM_WEBHOOK_ROUTES_KEY,
        value=serialized,
        value_kind="string",
        secret=True,
        updated_by=actor,
    )
    return enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")


@router.get("/routes", dependencies=[Depends(require_admin_key)])
async def get_telegram_routes() -> dict[str, Any]:
    from duckclaw.integrations.telegram.compact_webhook_routes import (
        parse_compact_telegram_webhook_routes,
    )

    resolved = telegram_webhook_routes_runtime_setting()
    raw = str(resolved.get("value") or "").strip()
    routes: list[dict[str, str]] = []
    fmt = "empty"
    if raw:
        if raw.startswith("["):
            fmt = "json"
        else:
            try:
                compact = parse_compact_telegram_webhook_routes(raw)
            except ValueError as exc:
                return {
                    "format": "invalid",
                    "routes": [],
                    "parse_error": str(exc),
                    "raw_masked": mask_secret(raw),
                    "known_bots": [],
                    "source": resolved.get("source", "default"),
                    "runtime_key": "telegram.webhook_routes",
                }
            if compact:
                fmt = "compact"
                routes = [
                    {
                        "bot": r.bot_name,
                        "path": r.webhook_path,
                        "worker_id": r.worker_id,
                        "tenant_id": r.tenant_id,
                        "vault_env_var": r.vault_env_var or "",
                        "token_masked": mask_secret(r.bot_token),
                    }
                    for r in compact
                ]
    return {
        "format": fmt,
        "routes": routes,
        "raw_masked": mask_secret(raw) if raw else "",
        "known_bots": [str(route.get("bot") or "") for route in routes],
        "source": resolved.get("source", "default"),
        "runtime_key": "telegram.webhook_routes",
    }


@router.put("/routes", dependencies=[Depends(require_admin_key)])
async def put_telegram_routes(
    body: TelegramRoutesPutBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.integrations.telegram.compact_webhook_routes import (
        TelegramCompactWebhookRoute,
        compact_route_to_path_binding,
        parse_compact_telegram_webhook_routes,
        serialize_compact_telegram_webhook_routes,
    )

    current = telegram_webhook_routes_runtime_setting()
    current_raw = str(current.get("value") or "").strip()
    current_by_bot = {
        r.bot_name: r for r in parse_compact_telegram_webhook_routes(current_raw)
    }

    built: list[TelegramCompactWebhookRoute] = []
    for inp in body.routes:
        bot = inp.bot.strip().lower()
        path = inp.path.strip()
        if not path.startswith("/api/v1/telegram/"):
            raise problem(
                400,
                "path inválido",
                f"Debe empezar por /api/v1/telegram/ (bot={bot})",
            )
        token_in = (inp.token or "").strip()
        if token_in:
            token = token_in
        elif bot in current_by_bot:
            token = current_by_bot[bot].bot_token
        else:
            raise problem(400, "Token requerido", f"Ruta nueva «{bot}» sin token de bot")
        worker_id = inp.worker_id.strip()
        tenant_id = inp.tenant_id.strip()
        if not worker_id or not tenant_id:
            raise problem(400, "worker/tenant requeridos", f"Ruta «{bot}» sin worker_id o tenant_id")
        vault_env = (inp.vault_env_var or "").strip()
        route = TelegramCompactWebhookRoute(
            bot_name=bot,
            bot_token=token,
            webhook_path=path,
            worker_id=worker_id,
            tenant_id=tenant_id,
            vault_env_var=vault_env,
        )
        try:
            compact_route_to_path_binding(route)
        except ValueError as exc:
            raise problem(400, "Ruta inválida", str(exc)) from exc
        built.append(route)

    try:
        serialized = serialize_compact_telegram_webhook_routes(built)
        parse_compact_telegram_webhook_routes(serialized)
    except ValueError as exc:
        raise problem(400, "Rutas inválidas", str(exc)) from exc

    task_id = upsert_telegram_webhook_routes_runtime_setting(serialized, actor=actor)
    admin_audit("telegram.routes.put", "telegram.webhook_routes", f"{len(built)} rutas", actor=actor)
    return {
        "ok": True,
        "updated": ["telegram.webhook_routes"],
        "task_id": task_id,
        "source": "db",
        "route_count": len(built),
        "restart_hint": "Reinicia DuckClaw-Gateway para registrar rutas dinámicas DB-first",
    }
