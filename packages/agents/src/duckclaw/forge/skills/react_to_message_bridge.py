"""Tool ``react_to_message``: the agent reacts to the user's message of this turn with an emoji.

The tool only queues the emoji (Redis ``duckclaw:chat_pending_reaction:{tenant}:{session}``, 10 min); the gateway applies it to the
user's message when it persists the turn (``core.chat_reactions.apply_pending_agent_reaction``), because only then does the stored
text of that message exist. Reactions are metadata: this never changes what the agent says or does.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List

from langchain_core.tools import StructuredTool

_log = logging.getLogger(__name__)
PENDING_TTL_SEC = 600


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
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as exc:
        _log.warning("react_to_message: redis failed: %s", exc)
        return json.dumps({"status": "error", "error": "redis_unavailable"}, ensure_ascii=False)
    return json.dumps({"status": "ok", "reaction": e}, ensure_ascii=False)


def register_react_to_message_skill(tools_list: List[Any], db: Any = None) -> None:
    def react_to_message(emoji: str) -> str:
        """Reacciona con un emoji al mensaje del usuario de este turno."""
        return react_to_message_impl(emoji)

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
