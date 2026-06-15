"""Shared graph tool names and safe fallback policy.

The DB-first worker catalog should provide the runtime tool surface. These
constants are compatibility fallbacks for legacy direct graph construction.
"""

from __future__ import annotations

from collections.abc import Iterable


DEFAULT_GENERAL_SYSTEM_PROMPT = (
    "Eres DuckClaw, un asistente general. Responde de forma concisa, usa las "
    "herramientas solo cuando aporten evidencia y no asumas permisos de "
    "escritura, red ni sandbox si no fueron configurados para este worker."
)

DEFAULT_GENERAL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "read_sql",
        "inspect_schema",
        "get_db_path",
    }
)

ADMIN_HEARTBEAT_SQL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "read_sql",
        "admin_sql",
        "inspect_schema",
        "get_schema_info",
    }
)

HEARTBEAT_TOOL_MESSAGES: dict[str, str] = {
    "get_schema_info": "🔎 Paso actual: entender columnas y tipos con get_schema_info...",
    "read_sql": "📊 Paso actual: consultar la base con read_sql (solo lectura)...",
    "run_sql": "📊 Paso actual: ejecutar SQL con run_sql...",
    "admin_sql": "📊 Paso actual: escritura SQL con admin_sql...",
    "run_sandbox": "⚙️ Paso actual: procesar o graficar en el sandbox (run_sandbox)...",
    "run_browser_sandbox": "🌐 Paso actual: navegación aislada en Strix browser (run_browser_sandbox)...",
    "get_browser_session_url": "🖥️ Paso actual: enlace noVNC para ver el navegador del sandbox...",
    "inspect_schema": "🗂️ Paso actual: listar qué hay en la base con inspect_schema...",
}


def normalize_tool_names(tool_names: Iterable[str] | None) -> frozenset[str]:
    """Normalize a configured tool list while preserving an explicit empty set."""

    if tool_names is None:
        return frozenset()
    return frozenset(
        str(name).strip()
        for name in tool_names
        if name is not None and str(name).strip()
    )


def default_general_tool_names(tool_names: Iterable[str] | None) -> frozenset[str]:
    """Return DB/caller-provided tool names or the safe legacy fallback."""

    if tool_names is None:
        return DEFAULT_GENERAL_TOOL_NAMES
    return normalize_tool_names(tool_names)


def heartbeat_message_for_tool_name(tool_name: str) -> str:
    """Return the generic heartbeat copy for a tool name."""

    name = str(tool_name or "").strip()
    if name in HEARTBEAT_TOOL_MESSAGES:
        return HEARTBEAT_TOOL_MESSAGES[name]
    return f"🔄 Paso actual: llamo a la herramienta {name}..."
