from __future__ import annotations

from typing import Any

import os

import httpx
from langchain_core.tools import tool

from duckclaw.graphs.on_the_fly_commands import append_task_audit
from duckclaw.graphs.graph_server import get_db


@tool
def send_proactive_message(chat_id: str, message: str) -> str:
    """
    Usa esta herramienta para enviar un mensaje proactivo o una alerta al usuario.
    Solo úsala cuando un [SYSTEM_EVENT] te lo solicite.
    """
    if not chat_id or not message:
        return "Uso: send_proactive_message(chat_id, message) con parámetros no vacíos."

    webhook_url = os.getenv("N8N_OUTBOUND_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return "N8N_OUTBOUND_WEBHOOK_URL no está configurado."

    headers: dict[str, Any] = {}
    auth_key = os.getenv("N8N_AUTH_KEY", "").strip()
    if auth_key:
        headers["X-DuckClaw-Secret"] = auth_key

    try:
        httpx.post(
            webhook_url,
            json={"chat_id": str(chat_id), "text": message},
            headers=headers,
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001
        return f"Error al enviar mensaje proactivo: {e}"

    # Auditoría básica en DuckDB
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
        # Auditoría best-effort; no romper la herramienta por esto.
        pass

    return "Mensaje enviado exitosamente al usuario."

