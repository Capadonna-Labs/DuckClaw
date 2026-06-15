"""Chat-scoped audit commands for the last runtime execution."""

from __future__ import annotations

import json
from typing import Any

from duckclaw.commands.chat_state import get_chat_state, set_chat_state


def execute_audit(db: Any, chat_id: Any) -> str:
    """/audit: evidencia de la última ejecución (SQL, latencia, run_id)."""
    raw = get_chat_state(db, chat_id, "last_audit")
    if not raw:
        return "No hay evidencia de última ejecución. Envía un mensaje y vuelve a usar /audit."
    try:
        data = json.loads(raw)
        sql = data.get("sql") or "(no registrado)"
        latency_ms = data.get("latency_ms") or "—"
        tokens = data.get("tokens") or "—"
        run_id = data.get("run_id") or "—"
        return (
            f"📋 Última ejecución\nSQL: {str(sql)[:300]}\nLatencia: {latency_ms} ms\nTokens: {tokens}\nLangSmith run_id: {run_id}"
        )
    except Exception:
        return "Datos de auditoría no válidos."


def save_last_audit(db: Any, chat_id: Any, latency_ms: int, sql: str = "", run_id: str = "", tokens: Any = None) -> None:
    """Guarda datos de la última ejecución para /audit."""
    data = {"latency_ms": latency_ms, "sql": sql or "", "run_id": run_id or "", "tokens": tokens or ""}
    set_chat_state(db, chat_id, "last_audit", json.dumps(data))
