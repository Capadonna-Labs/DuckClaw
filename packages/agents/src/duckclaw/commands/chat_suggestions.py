"""Sugerencias breves de continuación para el input del chat (post-turno, LLM, sin grafo)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from duckclaw.commands.model_setup import _effective_llm_triplet_for_chat_ui

_log = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 3
_MAX_SUGGESTION_CHARS = 80

_SYSTEM_PROMPT = (
    "Dado el último intercambio de una conversación de chat, propone exactamente "
    f"{_MAX_SUGGESTIONS} mensajes cortos (máximo 8 palabras cada uno) que el usuario "
    "podría escribir a continuación para seguir la conversación. Usa el mismo idioma "
    "del último mensaje del usuario. Responde ÚNICAMENTE con un array JSON de "
    f"{_MAX_SUGGESTIONS} strings, sin explicación ni markdown, por ejemplo: "
    '["...", "...", "..."]'
)


def _suggestions_globally_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_CHAT_SUGGESTIONS_ENABLED", "1") or "1").strip() != "0"


def _parse_suggestions(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        s = str(item).strip() if item is not None else ""
        if s:
            out.append(s[:_MAX_SUGGESTION_CHARS])
        if len(out) >= _MAX_SUGGESTIONS:
            break
    return out


def generate_followup_suggestions(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    last_user_text: str = "",
    last_assistant_text: str = "",
) -> list[str]:
    """Sugerencias cortas de continuación via LLM. Nunca levanta — degrada a ``[]``."""
    if not _suggestions_globally_enabled():
        return []
    assistant_text = (last_assistant_text or "").strip()
    if not assistant_text:
        return []
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from duckclaw.integrations.llm_providers import build_llm

        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        llm = build_llm(provider, model, base_url, db=db, tenant_id=tenant_id)
        if llm is None:
            return []
        human_content = (
            f"Usuario: {(last_user_text or '').strip()}\n\nAsistente: {assistant_text}"
        )
        reply = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_content)]
        )
        raw = str(getattr(reply, "content", "") or "")
        return _parse_suggestions(raw)
    except Exception as exc:
        _log.warning("chat_suggestions: generation failed: %s", exc)
        return []
