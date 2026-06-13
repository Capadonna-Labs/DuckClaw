"""
Validación de egress para OSINT JobHunter: bloquea respuestas con URLs plantilla o placeholders típicos del modelo.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Patrones que indican hardcodeo o ejemplos; no deben llegar al usuario como ofertas reales.
_BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"https?://[^\s)\]>'\"]*example\.(com|org|net)\b", re.IGNORECASE), "dominio example.*"),
    (re.compile(r"https?://[^\s)\]>'\"]*test\.example\b", re.IGNORECASE), "test.example"),
    (re.compile(r"\bpid=123456\b", re.IGNORECASE), "pid=123456"),
    (re.compile(r"https?://[^\s)\]>'\"]*localhost\b", re.IGNORECASE), "localhost"),
    (re.compile(r"https?://[^\s)\]>'\"]*127\.0\.0\.1\b", re.IGNORECASE), "127.0.0.1"),
]


def spec_is_job_hunter(spec: Any) -> bool:
    """True si la plantilla es Job-Hunter / job_hunter."""
    wid = (getattr(spec, "worker_id", None) or "").lower()
    lid = (getattr(spec, "logical_worker_id", None) or "").lower()
    a = re.sub(r"[^a-z0-9]", "", wid)
    b = re.sub(r"[^a-z0-9]", "", lid)
    return a == "jobhunter" or b == "jobhunter"


def job_hunter_reply_should_block(text: str) -> tuple[bool, Optional[str]]:
    """
    Si el mensaje final contiene URLs o patrones de plantilla, rechazar (no enviar al usuario tal cual).
    Retorna (True, motivo) para bloquear; (False, None) si pasa.
    """
    raw = (text or "").strip()
    if not raw:
        return False, None
    for pat, label in _BLOCK_PATTERNS:
        if pat.search(raw):
            return True, label
    return False, None


def job_hunter_blocked_reply_message(reason: str) -> str:
    """Texto sustituto cuando se bloquea la respuesta."""
    return (
        "La respuesta fue **filtrada**: se detectaron enlaces o patrones no confiables "
        f"({reason}). Solo deben mostrarse URLs literales devueltas por **tavily_search** o por "
        "**run_browser_sandbox**. Repite la petición para que el asistente invoque las herramientas de nuevo."
    )
