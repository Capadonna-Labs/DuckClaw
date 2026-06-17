"""Entry-route detection and inbound intent helpers for the manager."""

from __future__ import annotations

import re

from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.manager.fast_plans import _manager_visual_generation_intent
from duckclaw.manager.routing import _LONE_HTTP_URL_ONLY_LINE


def _worker_should_use_url_research_mcp_surface(text: str) -> bool:
    """
    Mensaje solo URL (HTTPS): omite GitHub/Trends/Reddit en cold start del grafo worker.
    Reddit MCP solo si la URL es reddit.com (``incoming_hint`` en build_worker_graph).
    """
    inc = (text or "").strip()
    if not _LONE_HTTP_URL_ONLY_LINE.match(inc):
        return False
    return not _manager_visual_generation_intent(inc)


def _duckdb_admin_write_intent(text: str) -> bool:
    """
    Mutaciones DuckDB (admin_sql / DDL) requieren un worker con política RW resuelta fuera del core.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    if re.search(r"\badmin_sql\b", t):
        return True
    if re.search(
        r"\b(create\s+table|alter\s+table|drop\s+table|truncate\s+table|"
        r"insert\s+into|delete\s+from)\b",
        t,
    ):
        return True
    if re.search(r"\bupdate\s+[a-z_][\w.]*\b", t):
        return True
    if re.search(
        r"\b(insert_deuda|insert_transaction|insert_cuenta|insert_presupuesto)\b",
        t,
    ):
        return True
    return False


def _is_goals_proactive_system_event(text: str) -> bool:
    """True si el mensaje es el SYSTEM_EVENT del ticker de /crons --delta (legado /goals; misma ruta HTTP)."""
    t = (text or "").strip()
    return t.startswith("[SYSTEM_EVENT:") and proactive_review_event_phrase_in_text(t)


def _is_entry_route_system_event(text: str) -> bool:
    """
    True si el inbound debe ejecutarse en ``entry_worker_id`` (worker de la ruta HTTP),
    sin que el manager lo reasigne (p. ej. eventos de ruta explícita hacia el worker de entrada).
    """
    return _is_goals_proactive_system_event(text)


__all__ = [
    "_duckdb_admin_write_intent",
    "_is_entry_route_system_event",
    "_is_goals_proactive_system_event",
    "_worker_should_use_url_research_mcp_surface",
]
