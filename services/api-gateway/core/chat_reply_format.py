"""Formateo y limpieza de respuestas de chat para Telegram y almacenamiento."""

from __future__ import annotations

import re


def truncate_log(s: str, max_len: int = 200) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def chat_identity_label(chat_id: str, username: str | None) -> str:
    cid = (chat_id or "").strip() or "unknown"
    uname = (username or "").strip()
    return f"@{uname} ({cid})" if uname else cid


def strip_markdown_bold(s: str) -> str:
    """Quita asteriscos de negrita Markdown (**texto**) para respuesta más limpia."""
    if not s or not isinstance(s, str):
        return s
    return re.sub(r"\*\*([^*]*)\*\*", r"\1", s)


def clean_agent_response(response: str) -> str:
    """
    Limpia menús residuales del LLM para que la respuesta final sea concisa.
    Quita líneas sueltas y bullets de menú sin truncar el resto del texto.
    """
    if not response or not isinstance(response, str):
        return response
    text = str(response)
    text = re.sub(r"(?is)<\s*pre\b[^>]*>", "", text)
    text = re.sub(r"(?is)<\s*/\s*pre\s*>", "", text)
    line_patterns = [
        r"(?im)^\s*¿Cuál\s+es\s+mi\s+tarea\?\s*$",
        r"(?im)^\s*¿Qué\s+te\s+gustaría\s+hacer\s+ahora\?\s*$",
        r"(?im)^-\s*📊\s*Resumen\s+financiero.*$",
        r"(?im)^-\s*💰\s*Registrar\s+transacciones.*$",
    ]
    for pattern in line_patterns:
        text = re.sub(pattern, "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def beautify_structured_insight_telegram(text: str) -> str:
    """Convierte encabezados tipo ## INSIGHT en líneas con emoji (mejor lectura en Telegram)."""
    if not text or not isinstance(text, str):
        return text
    t = text
    t = re.sub(r"(?im)^#+\s*\*?\*?INSIGHT:?\*?\*?\s*", "📌 INSIGHT — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?CAUSA:?\*?\*?\s*", "\n🔍 CAUSA — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?RECOMENDACIÓN:?\*?\*?\s*", "\n💡 RECOMENDACIÓN — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?RECOMENDACION:?\*?\*?\s*", "\n💡 RECOMENDACIÓN — ", t)
    t = re.sub(r"(?m)^#+\s+", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def strip_false_chart_delivery_lines(text: str) -> str:
    """Quita cierres que afirman envío de gráfico (el modelo no puede saber si Telegram recibió la foto)."""
    if not text or not isinstance(text, str):
        return text
    lines = text.splitlines()
    drop_phrases = (
        "se ha enviado en el chat",
        "se envió en el chat",
        "enviado en el chat",
        "grafico con el analisis completo",
        "gráfico con el análisis completo",
    )
    kept: list[str] = []
    for ln in lines:
        low = ln.lower()
        if any(p in low for p in drop_phrases) and ("gráfico" in low or "grafico" in low):
            continue
        kept.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
