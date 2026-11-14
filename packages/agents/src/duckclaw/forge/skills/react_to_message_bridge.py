"""Chat-UX tools of the admin chat: ``react_to_message`` (emoji on the user's message) and ``send_interim_message`` (a short message
sent while the agent keeps working, before the final answer).

The tool only queues the emoji (Redis ``duckclaw:chat_pending_reaction:{tenant}:{session}``, 10 min); the gateway applies it to the
user's message when it persists the turn (``core.chat_reactions.apply_pending_agent_reaction``), because only then does the stored
text of that message exist; it is also published live as an admin heartbeat (kind ``reaction``) so the UI shows it at once.
Interim messages are published live (kind ``message``) and queued (``duckclaw:chat_pending_interim:{tenant}:{session}``) so the gateway
stores them before the final answer when it persists the turn. Both only work in the admin web chat.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List

from langchain_core.tools import StructuredTool

_log = logging.getLogger(__name__)
PENDING_TTL_SEC = 600
INTERIM_MAX_PER_TURN = 3
INTERIM_MAX_CHARS = 280


def pending_interim_key(tenant_id: str, session_id: str) -> str:
    return f"duckclaw:chat_pending_interim:{(tenant_id or 'default').strip() or 'default'}:{(session_id or 'default').strip() or 'default'}"


def _publish_live(chat_id: str, text: str, kind: str) -> None:
    try:
        from duckclaw.graphs.chat_heartbeat import publish_admin_chat_heartbeat

        publish_admin_chat_heartbeat(chat_id, text, kind=kind)
    except Exception as exc:
        _log.debug("chat-ux live publish failed: %s", exc)


def pending_reaction_key(tenant_id: str, session_id: str) -> str:
    return f"duckclaw:chat_pending_reaction:{(tenant_id or 'default').strip() or 'default'}:{(session_id or 'default').strip() or 'default'}"


def react_to_message_impl(emoji: str) -> str:
    from duckclaw.forge.skills.goals_tool_context import get_goals_tool_chat_id, get_goals_tool_tenant_id
    from duckclaw.forge.skills.summarize_chat_context_bridge import _redis_url, _resolve_history_session_id

    e = (emoji or "").strip()
    if not (0 < len(e) <= 16) or e.isascii():
        return json.dumps({"status": "error", "error": "invalid_emoji", "hint": "Pasa un solo emoji, p. ej. 👍."}, ensure_ascii=False)
    chat_id = get_goals_tool_chat_id()
    url = _redis_url()
    if not chat_id or not url:
        return json.dumps({"status": "error", "error": "chat_unavailable", "hint": "react_to_message solo funciona dentro de un turno de chat."}, ensure_ascii=False)
    tenant_id = (get_goals_tool_tenant_id() or "default").strip() or "default"
    try:
        import redis

        client = redis.from_url(url, decode_responses=True)
        try:
            client.set(pending_reaction_key(tenant_id, _resolve_history_session_id(chat_id)), e, ex=PENDING_TTL_SEC)
            _publish_live(chat_id, e, "reaction")
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as exc:
        _log.warning("react_to_message: redis failed: %s", exc)
        return json.dumps({"status": "error", "error": "redis_unavailable"}, ensure_ascii=False)
    return json.dumps({"status": "ok", "reaction": e}, ensure_ascii=False)


def send_interim_message_impl(text: str) -> str:
    from duckclaw.forge.skills.goals_tool_context import get_goals_tool_chat_id, get_goals_tool_tenant_id
    from duckclaw.forge.skills.summarize_chat_context_bridge import _redis_url, _resolve_history_session_id
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    t = " ".join((text or "").split())
    if not t:
        return json.dumps({"status": "error", "error": "empty_text"}, ensure_ascii=False)
    if len(t) > INTERIM_MAX_CHARS:
        return json.dumps({"status": "error", "error": "too_long", "hint": f"Máximo {INTERIM_MAX_CHARS} caracteres: es un acuse, no la respuesta."}, ensure_ascii=False)
    chat_id = get_goals_tool_chat_id()
    url = _redis_url()
    if not chat_id or not url or not is_admin_ui_chat_session(chat_id):
        return json.dumps({"status": "error", "error": "chat_unavailable", "hint": "send_interim_message solo funciona en el chat web; responde normalmente."}, ensure_ascii=False)
    tenant_id = (get_goals_tool_tenant_id() or "default").strip() or "default"
    key = pending_interim_key(tenant_id, _resolve_history_session_id(chat_id))
    try:
        import redis

        client = redis.from_url(url, decode_responses=True)
        try:
            if client.llen(key) >= INTERIM_MAX_PER_TURN:
                return json.dumps({"status": "error", "error": "limit", "hint": f"Ya enviaste {INTERIM_MAX_PER_TURN} mensajes intermedios en este turno; sigue trabajando y da la respuesta final."}, ensure_ascii=False)
            client.rpush(key, t)
            client.expire(key, PENDING_TTL_SEC)
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as exc:
        _log.warning("send_interim_message: redis failed: %s", exc)
        return json.dumps({"status": "error", "error": "redis_unavailable"}, ensure_ascii=False)
    _publish_live(chat_id, t, "message")
    return json.dumps({"status": "ok", "sent": t, "hint": "Enviado. Sigue con el trabajo; no lo repitas en la respuesta final."}, ensure_ascii=False)


def register_react_to_message_skill(tools_list: List[Any], db: Any = None) -> None:
    def react_to_message(emoji: str) -> str:
        """Reacciona con un emoji al mensaje del usuario de este turno."""
        return react_to_message_impl(emoji)

    def send_interim_message(text: str) -> str:
        """Envía al usuario un mensaje corto ahora, mientras sigues trabajando."""
        return send_interim_message_impl(text)

    tools_list.append(
        StructuredTool.from_function(
            send_interim_message,
            name="send_interim_message",
            description=(
                "Envía YA un mensaje corto al usuario (máx. 280 caracteres, máx. 3 por turno) y sigues trabajando; luego da la respuesta final. "
                "Úsalo al empezar un trabajo largo (varias herramientas o análisis), con una frase breve y variada, p. ej. «Reviso eso y te cuento», "
                "o para avisar un hallazgo parcial. No es la respuesta: no pongas aquí resultados completos ni lo repitas al final. "
                "Solo en el chat web."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            react_to_message,
            name="react_to_message",
            description=(
                "Reacciona con un emoji al mensaje que el usuario acaba de enviar (como una reacción de chat). Úsala con moderación, "
                "para acusar recibo, celebrar o expresar algo breve sin escribir texto (👍 entendido, 🎉 buena noticia, 🙏 gracias). "
                "No sustituye la respuesta. emoji: un solo emoji."
            ),
        )
    )
