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

# Chips fijos de decisión binaria (índices 0 y 1). El tercero lo aporta el LLM.
_PROCEED_CHIP = "Procede"
_DO_NOT_PROCEED_CHIP = "No procede"

_SYSTEM_PROMPT = (
    "Dado el ÚLTIMO intercambio de una conversación, el UI mostrará exactamente "
    f"{_MAX_SUGGESTIONS} chips de continuación. "
    f'Los dos primeros están FIJOS: [0] "{_PROCEED_CHIP}" y [1] "{_DO_NOT_PROCEED_CHIP}". '
    "Tú solo propones el TERCER chip (una pregunta o pedido corto, máximo 8 palabras) "
    "alineado SOLO a temas/decisiones/datos de la respuesta más reciente del asistente "
    "(no a turnos anteriores). "
    "El tercer chip debe ser útil (riesgo, anomalía, aclaración, contraste), "
    "NO un atajo operativo tipo «confirma / ejecuta / re-registra / elimina». "
    "Usa el mismo idioma de la respuesta del asistente para el tercer chip "
    "(si el «usuario» es un [SYSTEM_EVENT] / ciclo /loop, ignora ese texto para el "
    "idioma y alinea al reporte). "
    "\n"
    "Elige recommended_index SOLO entre 0 y 1:\n"
    f'- 1 = "{_DO_NOT_PROCEED_CHIP}" (por defecto / sesgo prudente: hay riesgo, '
    "ambigüedad, fill parcial, señal absurda, falta de TP/SL, o la acción aún no "
    "está clara).\n"
    f'- 0 = "{_PROCEED_CHIP}" SOLO cuando sea prudente avanzar con la acción o '
    "corrección que el asistente acaba de proponer (clara, acotada, con datos "
    "consistentes y sin alarmas abiertas).\n"
    "Nunca pongas recommended_index=2. "
    "Responde ÚNICAMENTE con un objeto JSON (sin markdown) con esta forma exacta: "
    '{"third_suggestion":"...","recommended_index":1} '
    "(también aceptamos "
    '{"suggestions":["Procede","No procede","..."],"recommended_index":1}).'
)


def _suggestions_globally_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_CHAT_SUGGESTIONS_ENABLED", "1") or "1").strip() != "0"


def _normalize_proceed_triplet(
    third: str,
    recommended_raw: Any,
) -> dict[str, Any]:
    """Fija [Procede, No procede, tercero] y recommended_index ∈ {0,1} (default 1)."""
    third_clean = (third or "").strip()[:_MAX_SUGGESTION_CHARS]
    if not third_clean:
        # Fallback mínimo si el LLM no dio tercero útil.
        third_clean = "¿Qué riesgo queda abierto?"
    suggestions = [_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP, third_clean]
    # Default prudente: No procede. Solo 0 si el modelo elige Procede explícitamente.
    try:
        idx = int(recommended_raw)
    except (TypeError, ValueError):
        idx = 1
    if idx == 0:
        recommended = 0
    else:
        recommended = 1
    return {"suggestions": suggestions, "recommended_index": recommended}


def _parse_suggestions_payload(raw: str) -> dict[str, Any]:
    """Parse LLM output → ``{suggestions, recommended_index}`` con Procede/No procede."""
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

    recommended_raw: Any = 1
    third = ""
    if isinstance(data, dict):
        recommended_raw = data.get("recommended_index", data.get("recommended", 1))
        if isinstance(data.get("third_suggestion"), str):
            third = data["third_suggestion"]
        elif isinstance(data.get("suggestions"), list):
            items = data["suggestions"]
            # Si ya vienen 3, el tercero es el libre; si viene 1, es el tercero.
            if len(items) >= 3:
                third = str(items[2] or "")
            elif len(items) == 1:
                third = str(items[0] or "")
            elif len(items) == 2:
                # Legacy: tomar el último como ángulo libre.
                third = str(items[-1] or "")
            else:
                for item in items:
                    s = str(item).strip() if item is not None else ""
                    if s and s not in (_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP):
                        third = s
                        break
    elif isinstance(data, list):
        if len(data) >= 3:
            third = str(data[2] or "")
            recommended_raw = 1
        elif len(data) == 1:
            third = str(data[0] or "")
        elif data:
            third = str(data[-1] or "")
    else:
        return empty

    return _normalize_proceed_triplet(third, recommended_raw)


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
            f"Respuesta más reciente del asistente (alinea el 3er chip y "
            f"recommended_index a ESTO):\n{assistant_text}"
        )
        reply = llm.invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human_content)]
        )
        raw = str(getattr(reply, "content", "") or "")
        return _parse_suggestions_payload(raw)
    except Exception as exc:
        _log.warning("chat_suggestions: generation failed: %s", exc)
        return empty
