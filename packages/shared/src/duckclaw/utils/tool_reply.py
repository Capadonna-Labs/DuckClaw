"""Normalización de salidas de herramientas para egress (Telegram, trazas)."""

from __future__ import annotations

import json
import re
from typing import Any


def looks_like_tabular_account_rows_json(text: str) -> bool:
    """
    True si el texto es un JSON array de filas tipo cuenta tabular.
    """
    s = (text or "").strip()
    if not s.startswith("["):
        return False
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, list) or len(data) < 1:
        return False
    for row in data:
        if not isinstance(row, dict):
            return False
        if "name" not in row or "balance" not in row:
            return False
        if "currency" not in row and "updated_at" not in row:
            return False
    return True


def friendly_query_error(error_message: str) -> str | None:
    """Si el error de DuckDB incluye 'Did you mean', devuelve un mensaje corto; si no, None."""
    if not error_message or "Did you mean" not in error_message:
        return None
    m = re.search(r'Did you mean\s+"([^"]+)"\s*\?', error_message)
    if m:
        return f"La tabla no existe. ¿Quisiste decir: {m.group(1)}?"
    return "La tabla no existe. Revisa el nombre."


def format_tool_reply(raw: Any) -> str:
    """
    Convierte el resultado de una herramienta en texto para el usuario.
    Si el cuerpo parece JSON compacto, intenta formatearlo con sangría legible.
    """
    if raw is None:
        return "Listo."
    s = raw if isinstance(raw, str) else str(raw)
    s = s.strip()
    if not s:
        return "Listo."
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            obj = json.loads(s)
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    return s
