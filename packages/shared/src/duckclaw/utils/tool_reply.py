"""Normalización de salidas de herramientas para egress (Telegram, trazas)."""

from __future__ import annotations

import json
from typing import Any


def looks_like_finanz_local_cuentas_json(text: str) -> bool:
    """
    True si el texto es un JSON array de filas tipo ``finance_worker.cuentas``
    (id, name, balance, currency, updated_at).
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
