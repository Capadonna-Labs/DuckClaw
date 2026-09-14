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
    "Dado el ÚLTIMO intercambio de una conversación, propone exactamente "
    f"{_MAX_SUGGESTIONS} mensajes cortos (máximo 8 palabras cada uno) que el usuario "
    "podría enviar a continuación. "
    "Obligatorio: cada sugerencia debe referirse SOLO a temas, decisiones o datos "
    "mencionados en la respuesta más reciente del asistente (no a turnos anteriores). "
    "Usa el mismo idioma de la respuesta del asistente (si el «usuario» es un "
    "[SYSTEM_EVENT] / ciclo /loop, ignora ese texto para el idioma y alinea al reporte). "
    "\n"
    "Prioridad de utilidad (NO encadenes solo el siguiente paso operativo): "
    "las 3 sugerencias deben ser distintas entre sí y mezclar ángulos útiles, p. ej. "
    "(1) revisar riesgo/dato anómalo (distancias TP/SL, R:R, fills parciales, "
    "cantidades inconsistentes, señales stale), "
    "(2) pedir explicación o contraste de un hallazgo concreto, "
    "(3) una alternativa o decisión no obvia. "
    "Evita chips que solo confirmen/ejecuten/aprueben el siguiente paso "
    "(p. ej. «confirma las OCAs», «ejecuta el batch», «re-registra TP/SL», "
    "«elimina la señal stale», «sí, adelante») salvo que el usuario YA haya "
    "pedido explícitamente esa acción en su último mensaje. "
    "Prefiere preguntas que ayuden a decidir con criterio, no atajos de workflow. "
    "\n"
    'Excepción prudente: puedes incluir exactamente la sugerencia "Procede" '
    "(una de las tres) cuando sea prudente avanzar con la acción o corrección "
    "que el asistente acaba de proponer — clara, acotada, con datos consistentes "
    "y sin alarmas abiertas. Si usas \"Procede\", puede ser la recomendada "
    "(recommended_index apuntando a ese ítem). Si no es prudente avanzar, "
    "NO uses \"Procede\"; prioriza chips de riesgo/aclaración. "
    "\n"
    "Elige además la MEJOR sugerencia (recommended_index): la más útil para "
    "entender riesgo o resolver una ambigüedad — o \"Procede\" cuando sí sea "
    "prudente avanzar. "
    "Responde ÚNICAMENTE con un objeto JSON (sin markdown) con esta forma exacta: "
    '{"suggestions":["...","...","..."],"recommended_index":0} '
    f"donde recommended_index es un entero 0..{_MAX_SUGGESTIONS - 1}."
)


def _suggestions_globally_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_CHAT_SUGGESTIONS_ENABLED", "1") or "1").strip() != "0"


def _clamp_recommended_index(raw: Any, n: int) -> int:
    if n <= 0:
        return 0
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return 0
    if idx < 0 or idx >= n:
        return 0
    return idx


def _parse_suggestions_payload(raw: str) -> dict[str, Any]:
    """Parse LLM output → ``{suggestions, recommended_index}``. Accepts legacy JSON arrays."""
    empty: dict[str, Any] = {"suggestions": [], "recommended_index": 0}
    text = (raw or "").strip()
    if not text:
        return empty
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return empty

    recommended_raw: Any = 0
    items: list[Any]
    if isinstance(data, dict):
        items = data.get("suggestions") if isinstance(data.get("suggestions"), list) else []
        recommended_raw = data.get("recommended_index", data.get("recommended", 0))
    elif isinstance(data, list):
        items = data
    else:
        return empty

    out: list[str] = []
    for item in items:
        s = str(item).strip() if item is not None else ""
        if s:
            out.append(s[:_MAX_SUGGESTION_CHARS])
        if len(out) >= _MAX_SUGGESTIONS:
            break
    return {
        "suggestions": out,
        "recommended_index": _clamp_recommended_index(recommended_raw, len(out)),
    }


def generate_followup_suggestions(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    last_user_text: str = "",
    last_assistant_text: str = "",
) -> dict[str, Any]:
    """Sugerencias + índice recomendado via LLM. Nunca levanta — degrada a vacío."""
    empty: dict[str, Any] = {"suggestions": [], "recommended_index": 0}
    if not _suggestions_globally_enabled():
        return empty
    assistant_text = (last_assistant_text or "").strip()
    if not assistant_text:
        return empty
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from duckclaw.integrations.llm_providers import build_llm

        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        llm = build_llm(provider, model, base_url, db=db, tenant_id=tenant_id)
        if llm is None:
            return empty
        human_content = (
            f"Último mensaje del usuario: {(last_user_text or '').strip()}\n\n"
            f"Respuesta más reciente del asistente (alinea las sugerencias a ESTO):\n{assistant_text}"
        )
        reply = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_content)]
        )
        raw = str(getattr(reply, "content", "") or "")
        return _parse_suggestions_payload(raw)
    except Exception as exc:
        _log.warning("chat_suggestions: generation failed: %s", exc)
        return empty
