from __future__ import annotations

from langchain_core.tools import tool

from duckclaw.graphs.on_the_fly_commands import append_task_audit
from duckclaw.graphs.graph_server import get_db
from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.integrations.telegram.telegram_outbound_sync import send_bot_message_sync
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html


@tool
def send_proactive_message(chat_id: str, message: str) -> str:
    """
    Usa esta herramienta para enviar un mensaje proactivo o una alerta al usuario.
    Solo úsala cuando un [SYSTEM_EVENT] te lo solicite.
    """
    if not chat_id or not message:
        return "Uso: send_proactive_message(chat_id, message) con parámetros no vacíos."

    token = (effective_telegram_bot_token_outbound() or "").strip()
    if not token:
        return "TELEGRAM_BOT_TOKEN (o token del bot en .env) no está configurado."

    try:
        ok = send_bot_message_sync(
            bot_token=token,
            chat_id=str(chat_id),
            text=llm_markdown_to_telegram_html(message),
            parse_mode="HTML",
            timeout_sec=15.0,
        )
        if not ok:
            return "No se pudo entregar el mensaje por Bot API de Telegram."
    except Exception as e:  # noqa: BLE001
        return f"Error al enviar mensaje proactivo: {e}"

    try:
        db = get_db()
        append_task_audit(
            db,
            chat_id,
            "send_proactive_message",
            message[:200],
            "PROACTIVE_MESSAGE_SENT",
            0,
        )
    except Exception:
        pass

    return "Mensaje enviado exitosamente al usuario."
