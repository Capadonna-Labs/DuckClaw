"""Generic task-intent classification helpers for the manager graph."""

from __future__ import annotations

import re


def _incoming_has_context_summary_system_directive(incoming: str) -> bool:
    """Return True for gateway context-summary directives."""
    text = incoming or ""
    return (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in text
        or "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in text
    )


def _incoming_looks_like_semantic_context_followup(incoming: str) -> bool:
    """
    Heuristic: the user asks about indexed notes without pasting the full body.
    This is generic routing pressure for a light tool surface.
    """
    raw = (incoming or "").strip()
    if not raw or _incoming_has_context_summary_system_directive(raw):
        return False
    text = raw.lower()
    if re.search(
        r"\b(qué|que|hay|algo)\s+.+\s+(en el contexto|en mi contexto|en la memoria)\b",
        text,
    ):
        return True
    if re.search(r"\b(en el contexto|en mi contexto|en la memoria)\s*\?", text):
        return True
    if re.search(
        r"\b(tenemos anotado|hay anotado|notas sobre|contexto indexado|memoria semántica|memoria semantica)\b",
        text,
    ):
        return True
    return "search_semantic" in text


def _worker_should_use_lite_stdio_mcp_surface(text: str) -> bool:
    return _incoming_has_context_summary_system_directive(text) or _incoming_looks_like_semantic_context_followup(
        text
    )


def _text_has_word_boundary(term: str, text: str) -> bool:
    if not term or not text:
        return False
    return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE))


__all__ = [
    "_incoming_has_context_summary_system_directive",
    "_incoming_looks_like_semantic_context_followup",
    "_text_has_word_boundary",
    "_worker_should_use_lite_stdio_mcp_surface",
]
