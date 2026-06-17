"""Entrega outbound de texto chat (Telegram Bot API / MCP, Discord followup)."""

from __future__ import annotations

import logging
from typing import Any

from duckclaw.channels import GatewayDeliveryContext
from duckclaw.integrations.telegram.telegram_agent_token import (
    canonical_manifest_worker_id,
    resolve_telegram_token_for_worker_id,
    telegram_worker_ids_match_for_compact_route,
)
from duckclaw.utils.logger import format_chat_id_for_terminal

_gateway_log = logging.getLogger("duckclaw.gateway")


def effective_telegram_bot_token() -> str:
    """Token Bot API para este proceso (tras overrides PM2 + per-gateway + ContextVar multiplex)."""
    from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound

    return effective_telegram_bot_token_outbound()


def telegram_token_from_compact_routes_for_worker(worker_id: str) -> str:
    """Fallback: resuelve token por worker desde DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES."""
    try:
        from duckclaw.integrations.telegram.compact_webhook_routes import load_path_webhook_bindings_from_env

        if not (worker_id or "").strip():
            return ""
        for b in load_path_webhook_bindings_from_env():
            if telegram_worker_ids_match_for_compact_route(worker_id, b.worker_id):
                return str(b.bot_token or "").strip()
    except Exception:
        return ""
    return ""


def strip_lines_mentioning_workspace_output(text: str) -> str:
    """Quita líneas que citan rutas del sandbox (/workspace/output/...) para no confundir al usuario en Telegram."""
    if not text or "/workspace/output/" not in text:
        return text
    lines = (text or "").splitlines()
    kept = [ln for ln in lines if "/workspace/output/" not in ln]
    out = "\n".join(kept).strip()
    return out if out else text


def outbound_deliver_chat_text_sync(
    *,
    chat_id: str,
    user_id: str,
    text: str,
    worker_id: str | None = None,
    outbound_telegram_bot_token: str | None = None,
    prefer_native_bot_api: bool = False,
    telegram_mcp: Any = None,
    redis_url: str | None = None,
    tenant_id: str = "default",
) -> bool:
    """Entrega texto largo al usuario: MCP (si hay sesión) y luego Bot API nativa."""
    from duckclaw.graphs.chat_heartbeat import normalize_telegram_chat_id_for_outbound

    cid_raw = str(chat_id or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid_raw = str(user_id or "").strip()
    uid = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid
    raw = (text or "").strip()
    if not cid or not raw:
        _gateway_log.warning(
            "outbound deliver: omitido (chat_id=%s text vacío=%s)",
            format_chat_id_for_terminal(cid or cid_raw),
            not bool(raw),
        )
        return False

    if telegram_mcp is not None and not prefer_native_bot_api:
        try:
            from duckclaw.forge.skills.telegram_mcp_bridge import run_async, send_long_plain_via_mcp_chunks

            ok = run_async(
                send_long_plain_via_mcp_chunks(telegram_mcp.session, chat_id=str(cid), plain_text=raw),
            )
            if ok:
                _gateway_log.info(
                    "outbound deliver: MCP OK chat_id=%s len_text=%s",
                    format_chat_id_for_terminal(cid),
                    len(raw),
                )
                return True
            _gateway_log.warning("outbound deliver: MCP no entregó todo; fallback nativo chat_id=%s", cid)
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("outbound deliver: MCP error %s; fallback nativo", exc)
            try:
                from core.telegram_mcp_dlq import push_telegram_mcp_dlq_blocking

                push_telegram_mcp_dlq_blocking(
                    redis_url,
                    tenant_id=tenant_id,
                    chat_id=str(cid),
                    tool="telegram_send_message",
                    args={"chat_id": str(cid), "text": "<outbound disconnect fallback>"},
                    error=str(exc)[:2000],
                )
            except Exception:
                pass

    token = (outbound_telegram_bot_token or "").strip()
    if not token:
        try:
            token = (resolve_telegram_token_for_worker_id((worker_id or "").strip()) or "").strip()
        except Exception:
            token = ""
    if not token:
        token = telegram_token_from_compact_routes_for_worker((worker_id or "").strip())
    if not token:
        token = effective_telegram_bot_token()
        if not token:
            _wid = canonical_manifest_worker_id((worker_id or "").strip())
            _gateway_log.warning(
                "outbound deliver: sin token Bot API para worker_id=%r. Defina TELEGRAM_%s_TOKEN, "
                "TELEGRAM_BOT_TOKEN o entrada en DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES.",
                worker_id,
                (_wid or "WORKER").replace("-", "_").upper(),
            )
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            _gateway_log.info(
                "outbound deliver: intento Bot API nativo chat_id=%s len_text=%s",
                format_chat_id_for_terminal(cid),
                len(raw),
            )
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=raw,
                log=_gateway_log,
            )
            if n > 0:
                _gateway_log.info(
                    "outbound deliver: Bot API OK chat_id=%s partes=%s",
                    format_chat_id_for_terminal(cid),
                    n,
                )
                return True
            _gateway_log.warning(
                "outbound deliver: Bot API no envió partes (chat_id=%s)",
                format_chat_id_for_terminal(cid),
            )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning(
                "outbound deliver: error Bot API chat_id=%s: %s",
                format_chat_id_for_terminal(cid),
                exc,
            )

    return False


def deliver_outbound_by_channel(
    dc: GatewayDeliveryContext,
    *,
    chat_id: str,
    user_id: str,
    text: str,
    worker_id: str | None,
    tenant_id: str,
    redis_url: str | None,
    prefer_native_bot_api: bool = False,
) -> bool:
    """Entrega best-effort según canal (Telegram: MCP/Bot API; Discord: PATCH @original)."""
    ch = (dc.channel or "telegram").strip().lower()
    if ch == "telegram":
        return outbound_deliver_chat_text_sync(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            worker_id=worker_id,
            outbound_telegram_bot_token=dc.outbound_bot_token,
            prefer_native_bot_api=prefer_native_bot_api or dc.prefer_native_bot_api,
            telegram_mcp=dc.telegram_mcp,
            redis_url=redis_url,
            tenant_id=tenant_id,
        )
    if ch == "discord":
        from core.discord_interactions import discord_followup_edit_original_sync

        return discord_followup_edit_original_sync(
            application_id=(dc.discord_application_id or "").strip(),
            interaction_token=(dc.discord_interaction_token or "").strip(),
            bot_token=(dc.outbound_bot_token or "").strip(),
            content=text or "",
        )
    _gateway_log.warning("deliver outbound: canal desconocido %r", dc.channel)
    return False
