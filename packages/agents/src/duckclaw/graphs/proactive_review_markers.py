"""Marcas de texto para el SYSTEM_EVENT del ticker programado (/crons --delta). Sin dependencias pesadas."""

from __future__ import annotations

# Marca en SYSTEM_EVENT del ticker proactivo (heartbeat). Se reconoce también la frase heredada con /goals.
GOALS_PROACTIVE_REVIEW_PHRASE_CRONS = "Revisión periódica de /crons"
GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY = "Revisión periódica de /goals"


def proactive_review_event_phrase_in_text(text: str) -> bool:
    """True si el texto incluye la marca del tick programado vía ``/crons --delta`` (o legado ``/goals``)."""
    t = text or ""
    return GOALS_PROACTIVE_REVIEW_PHRASE_CRONS in t or GOALS_PROACTIVE_REVIEW_PHRASE_LEGACY in t
