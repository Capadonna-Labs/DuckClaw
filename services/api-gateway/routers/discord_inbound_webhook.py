"""
Ingress Discord Interactions → mismo pipeline `_invoke_chat` que Telegram.

Contrato y env: véase specs/features/telegram-gateway/GATEWAY_AGNOSTIC_CHANNELS.md
Variables: DISCORD_PUBLIC_KEY o DUCKCLAW_DISCORD_PUBLIC_KEY, DUCKCLAW_DISCORD_BOT_TOKEN,
  DUCKCLAW_DISCORD_DEFAULT_WORKER_ID (opcional), DUCKCLAW_CHANNEL_ROUTES, DUCKCLAW_DISCORD_BYPASS_GUARD.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from core.discord_interactions import (
    discord_followup_edit_original_sync,
    discord_interaction_deferred_payload,
    parse_slash_duckclaw,
    verify_discord_request_signature,
)
from core.models import ChatRequest

from duckclaw.channels import GatewayDeliveryContext, build_discord_session_id, resolve_discord_route

_log = logging.getLogger(__name__)


def build_discord_interactions_router(
    *,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    app_state_holder: Any,
) -> APIRouter:
    router = APIRouter(tags=["discord-interactions"])

    @router.post("/api/v1/discord/interactions")
    async def discord_interactions_endpoint(request: Request) -> JSONResponse:
        pubkey = (
            os.environ.get("DISCORD_PUBLIC_KEY")
            or os.environ.get("DUCKCLAW_DISCORD_PUBLIC_KEY")
            or ""
        ).strip()
        if not pubkey:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DUCKCLAW_DISCORD_PUBLIC_KEY no configurado",
            )

        raw = await request.body()
        sig = (request.headers.get("x-signature-ed25519") or "").strip()
        ts = (request.headers.get("x-signature-timestamp") or "").strip()

        if not verify_discord_request_signature(
            body=raw, signature_hex=sig, timestamp_header=ts, public_key_hex=pubkey
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="firma inválida")

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        itype = payload.get("type")
        if itype == 1:
            return JSONResponse({"type": 1})

        if itype != 2:
            return JSONResponse(discord_interaction_deferred_payload(), status_code=200)

        text, err = parse_slash_duckclaw(payload)
        user_obj = (payload.get("member") or {}).get("user") if isinstance(payload.get("member"), dict) else None
        if not isinstance(user_obj, dict):
            user_obj = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        user_id = str(user_obj.get("id") or "").strip()
        guild_id = str(payload.get("guild_id") or "").strip()
        channel_id = str(payload.get("channel_id") or "").strip()
        app_id = str(payload.get("application_id") or "").strip()
        interaction_token = str(payload.get("token") or "").strip()
        username = (
            str(user_obj.get("username") or user_obj.get("global_name") or "DiscordUser").strip()
            or "DiscordUser"
        )

        if err or not text:
            return JSONResponse(
                {"type": 4, "data": {"content": err or "vacío", "flags": 64}},
            )

        route_binding = resolve_discord_route(guild_id=guild_id if guild_id else None)
        from duckclaw.forge.team_env import default_worker_id_from_env

        default_worker = (
            os.environ.get("DUCKCLAW_DISCORD_DEFAULT_WORKER_ID") or default_worker_id_from_env()
        ).strip()
        tenant = route_binding.tenant_id if route_binding else "default"
        worker_id = route_binding.worker_id if route_binding else default_worker
        bot_env = route_binding.bot_token_env if route_binding else "DUCKCLAW_DISCORD_BOT_TOKEN"
        bot_token = (os.environ.get(bot_env) or os.environ.get("DUCKCLAW_DISCORD_BOT_TOKEN") or "").strip()
        if not bot_token:
            raise HTTPException(
                status_code=503,
                detail=f"Sin token bot ({bot_env} / DUCKCLAW_DISCORD_BOT_TOKEN)",
            )

        forced_vault_path: str | None = None
        if route_binding and route_binding.vault_db_env:
            forced_vault_path = (os.environ.get(route_binding.vault_db_env) or "").strip() or None

        session_id = build_discord_session_id(guild_id or "dm", channel_id or "unknown", user_id or "anon")
        chat_req = ChatRequest(
            message=text,
            chat_id=session_id,
            user_id=user_id or session_id,
            username=username,
            chat_type="supergroup",
            tenant_id=tenant,
            vault_db_path=forced_vault_path,
        )

        redis_client = getattr(app_state_holder, "redis", None)

        bypass = (
            os.getenv("DUCKCLAW_DISCORD_BYPASS_GUARD", "").strip().lower() in ("1", "true", "yes", "on")
        )

        dc = GatewayDeliveryContext(
            channel="discord",
            outbound_bot_token=bot_token,
            discord_application_id=app_id,
            discord_interaction_token=interaction_token,
            discord_guild_id=guild_id or None,
            discord_channel_id=channel_id or None,
            telegram_forced_vault_db_path=forced_vault_path,
            extra={"discord_bypass_guard": bypass},
        )

        async def _run_agent() -> None:
            try:
                res = await invoke_agent_chat(
                    chat_req,
                    worker_id,
                    session_id,
                    tenant,
                    redis_client=redis_client,
                    telegram_multipart_tail_delivery=None,
                    telegram_mcp=None,
                    telegram_forced_vault_db_path=forced_vault_path,
                    outbound_telegram_bot_token=None,
                    delivery_context=dc,
                )
            except Exception as exc:
                _log.warning("Discord agent error: %s", exc)
                discord_followup_edit_original_sync(
                    application_id=app_id,
                    interaction_token=interaction_token,
                    bot_token=bot_token,
                    content=f"Error: {exc}",
                )
                return

            reply = (res.get("response") or "").strip() if isinstance(res, dict) else ""
            discord_followup_edit_original_sync(
                application_id=app_id,
                interaction_token=interaction_token,
                bot_token=bot_token,
                content=reply or "(sin contenido)",
            )

        asyncio.create_task(_run_agent())
        return JSONResponse(discord_interaction_deferred_payload())

    return router
