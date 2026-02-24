"""Formateo de respuestas de herramientas para mostrar al usuario."""

from __future__ import annotations

import json
import re


def friendly_query_error(error_message: str) -> str | None:
    """Si el error de DuckDB incluye 'Did you mean', devuelve un mensaje corto; si no, None."""
    if not error_message or "Did you mean" not in error_message:
        return None
    # DuckDB: '... Did you mean "telegram_messages"? ...'
    m = re.search(r'Did you mean\s+"([^"]+)"\s*\?', error_message)
    if m:
        return f"La tabla no existe. ¿Quisiste decir: {m.group(1)}?"
    return "La tabla no existe. Revisa el nombre."


def format_tool_reply(raw: str) -> str:
    """Convierte el resultado crudo de una herramienta en un mensaje legible para el usuario."""
    if not raw or not raw.strip():
        return "Sin resultados."
    s = raw.strip()
    # Si es un array JSON de objetos (ej. list_tables, resultados SQL)
    if s.startswith("["):
        try:
            data = json.loads(s)
            if not isinstance(data, list):
                return s
            if not data:
                return "No hay resultados."
            # list_tables: [{"table_name": "x"}, ...]
            if isinstance(data[0], dict) and "table_name" in data[0]:
                names = [str(row.get("table_name", "")) for row in data]
                return "Las tablas en la base de datos son: " + ", ".join(names) + "."
            # Lista genérica de filas
            if len(data) <= 5 and isinstance(data[0], dict):
                lines = []
                for i, row in enumerate(data):
                    parts = [f"{k}: {v}" for k, v in (row or {}).items()]
                    lines.append("  " + " | ".join(parts))
                return "Resultado:\n" + "\n".join(lines)
            return f"Se encontraron {len(data)} registro(s)." if len(data) > 3 else s
        except (json.JSONDecodeError, TypeError, IndexError, KeyError):
            pass
    # Si es un objeto JSON con "error", mensaje amigable para el usuario
    if s.startswith("{"):
        try:
            data = json.loads(s)
            if isinstance(data, dict) and "error" in data:
                err = str(data.get("error", ""))
                friendly = friendly_query_error(err)
                if friendly:
                    return friendly
                if "Catalog Error" in err or "Table" in err or "does not exist" in err:
                    return "Esa tabla no existe en la base de datos. Pregunta por las tablas disponibles o revisa el nombre."
                if "Query vacío" in err or "vacío" in err:
                    return "No se envió ninguna consulta."
                return "No se pudo completar la operación. Revisa la consulta o los datos."
            return s  # dejamos JSON si es objeto (inventario, etc.)
        except (json.JSONDecodeError, TypeError):
            pass
    return s
