"""
Transversal answer/evidence validation helpers for worker egress.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

from langchain_core.messages import SystemMessage, ToolMessage

# Decimal figure with at least 2 fractional digits or a $ prefix.
_DECIMAL_FIGURE_PAT = re.compile(r"(?:\$\s*)?(\d{1,6}\.\d{2,6})\b")
_PCT_FIGURE_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%")
_VLM_MARKER = "VLM_CONTEXT"
_VLM_GATEWAY_BLOCK = "Contexto visual adjunto:"
_VLM_CONFIDENCE_RE = re.compile(
    r"\[VLM_CONTEXT[^\]]*confidence=([\d.]+)\]",
    re.IGNORECASE,
)
_GATEWAY_VLM_MIN_CONFIDENCE = 0.5
_EVIDENCE_TOOLS = {"read_sql", "verify_visual_claim"}
_NUMERIC_VERIFY_STATUSES = frozenset({"verified", "mismatch", "no_evidence"})

VISUAL_EVIDENCE_RETRY_REASON = "missing_tool_evidence_for_vlm_claim"

_VISUAL_EVIDENCE_USER_ERROR = (
    "❌ Regla de Evidencia Única: detecté contexto visual y cifras numéricas sin tool call válido en este turno. "
    "Ejecuta read_sql o verify_visual_claim primero y luego recalculo."
)

_VISUAL_EVIDENCE_RETRY_DIRECTIVE = (
    "Contexto VLM con cifras numéricas detectadas en tu borrador. "
    "Ejecuta read_sql o verify_visual_claim en este turno "
    "antes de redactar cifras. No cites números sin un ToolMessage válido de evidencia."
)


def _tool_message_satisfies_visual_evidence(m: ToolMessage) -> bool:
    nm = str(getattr(m, "name", "") or "").strip()
    content = str(getattr(m, "content", "") or "")
    low = content.lower()
    if nm in _EVIDENCE_TOOLS and "error" not in low:
        return True
    if nm == "verify_visual_claim":
        if "error" in low:
            return False
        try:
            data = json.loads(content)
            if isinstance(data, dict) and data.get("status") in _NUMERIC_VERIFY_STATUSES:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def visual_evidence_retry_system_message() -> SystemMessage:
    """Internal retry instruction for the worker graph."""
    return SystemMessage(content=_VISUAL_EVIDENCE_RETRY_DIRECTIVE)


def _incoming_has_gateway_vlm_evidence(inc: str) -> bool:
    """
    Playground/Telegram gateway already ran VLM and injected structured evidence.
    That block is sufficient; do not force read_sql/verify_visual_claim on top.
    """
    if _VLM_MARKER not in inc or _VLM_GATEWAY_BLOCK not in inc:
        return False
    m = _VLM_CONFIDENCE_RE.search(inc)
    if not m:
        return True
    try:
        return float(m.group(1)) >= _GATEWAY_VLM_MIN_CONFIDENCE
    except ValueError:
        return True


def enforce_visual_evidence_rule(
    *,
    incoming: str,
    messages: list[Any],
    reply: str,
    db: Any = None,
    spec: Any = None,
) -> Tuple[str, Optional[str]]:
    """
    Require same-turn tool evidence before quoting visual-context numeric figures.
    """
    inc = (incoming or "").strip()
    text = (reply or "").strip()
    if not inc or _VLM_MARKER not in inc:
        return reply, None
    has_numeric_figure = bool(_DECIMAL_FIGURE_PAT.search(text) or _PCT_FIGURE_RE.search(text))
    gateway_vlm = _incoming_has_gateway_vlm_evidence(inc)
    if gateway_vlm:
        return reply, None
    if not has_numeric_figure:
        return reply, None

    for m in messages or []:
        if isinstance(m, ToolMessage) and _tool_message_satisfies_visual_evidence(m):
            return reply, None
    return (_VISUAL_EVIDENCE_USER_ERROR, VISUAL_EVIDENCE_RETRY_REASON)


__all__ = [
    "VISUAL_EVIDENCE_RETRY_REASON",
    "enforce_visual_evidence_rule",
    "visual_evidence_retry_system_message",
]
