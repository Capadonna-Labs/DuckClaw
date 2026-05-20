from __future__ import annotations

"""
SendPrivateMessage skill — enrutamiento cruzado (DM) vía Bot API / webhook.

Contrato: send_dm(user_id: str, text: str)
Implementación: Bot API nativa; webhook opcional vía DUCKCLAW_SEND_DM_WEBHOOK_URL.
"""

import json
import os
from typing import Any, Optional


def _send_dm_tool(config: Optional[dict] = None) -> Optional[Any]:
    """
    Crea un StructuredTool para enviar mensajes privados (DM).

    Requiere TELEGRAM_BOT_TOKEN o token del bot activo; opcionalmente
    DUCKCLAW_SEND_DM_WEBHOOK_URL + DUCKCLAW_OUTBOUND_WEBHOOK_SECRET.
    """
    cfg = config or {}
    if cfg.get("enabled") is False:
        return None

    webhook_url = cfg.get("webhook_url") or os.environ.get("DUCKCLAW_SEND_DM_WEBHOOK_URL", "").strip()

    try:
        from langchain_core.tools import StructuredTool
    except Exception:
        return None

    def _send_dm(user_id: str, text: str) -> str:
        from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
        from duckclaw.integrations.telegram.telegram_outbound_sync import send_bot_message_sync
        from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html

        user_id_str = (user_id or "").strip()
        if not user_id_str:
            return "Debes indicar user_id para enviar un DM."
        safe = llm_markdown_to_telegram_html(text or "")

        token = (effective_telegram_bot_token_outbound() or "").strip()
        if token and send_bot_message_sync(
            bot_token=token,
            chat_id=user_id_str,
            text=safe,
            parse_mode="HTML",
        ):
            return "DM enviado por Bot API."

        if not webhook_url:
            return "Sin TELEGRAM_BOT_TOKEN ni DUCKCLAW_SEND_DM_WEBHOOK_URL; no se envió el DM."

        import urllib.request

        payload = {"user_id": user_id_str, "chat_id": user_id_str, "text": safe, "parse_mode": "HTML"}
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = (os.environ.get("DUCKCLAW_OUTBOUND_WEBHOOK_SECRET") or "").strip()
        if secret:
            headers["X-DuckClaw-Secret"] = secret
        req = urllib.request.Request(webhook_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 201, 202):
                    return "DM enviado (webhook)."
                return f"Webhook respondió status={resp.status}."
        except Exception as e:  # noqa: BLE001
            return f"No se pudo enviar el DM: {e}"

    return StructuredTool.from_function(
        _send_dm,
        name="send_dm",
        description=(
            "Envía un mensaje privado (DM) a un usuario. "
            "Parámetros: user_id (chat_id de Telegram), text (contenido)."
        ),
    )


def register_send_dm_skill(
    tools_list: list[Any],
    send_dm_config: Optional[dict] = None,
) -> None:
    """Registra la herramienta send_dm en la lista de tools."""
    if not send_dm_config:
        send_dm_config = {"enabled": True}
    try:
        tool = _send_dm_tool(send_dm_config)
        if tool:
            tools_list.append(tool)
    except Exception:
        return
