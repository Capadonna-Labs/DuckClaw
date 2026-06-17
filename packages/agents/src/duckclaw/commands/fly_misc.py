"""Comandos fly transversales menores: /tasks, /help, /lake, /approve, /reject."""

from __future__ import annotations

import time
from typing import Any

from duckclaw.commands.sensors import _lake_ssh_status_lines
from duckclaw.guardrails.loader import load_guardrail, load_guardrail_pipe_table


def execute_approve_reject(db: Any, chat_id: Any, approved: bool) -> str:
    """/approve o /reject: HITL (grafo en interrupt). Sin interrupt implementado: mensaje informativo."""
    _ = db, chat_id, approved
    return "No hay operación pendiente de aprobación. (El grafo no está en estado interrupt en esta versión.)"


def execute_tasks(db: Any, chat_id: Any) -> str:
    """/tasks: estado del ActivityManager (Redis): IDLE, BUSY, subagente, tarea actual, tiempo en ejecución."""
    # Import graph-local: activity vive en graphs por acoplamiento Redis/runtime.
    from duckclaw.graphs.activity import get_activity

    data = get_activity(chat_id)
    if data is None:
        return "⏸ IDLE (Redis no configurado)."
    status = data.get("status", "IDLE")
    task = data.get("task", "")
    worker_id = data.get("worker_id", "") or ""
    started_at = data.get("started_at", 0)
    elapsed_s = ""
    if started_at and status == "BUSY":
        try:
            elapsed_s = f" · {int(time.time()) - int(started_at)}s"
        except Exception:
            pass
    worker_display = (worker_id or "").replace("-", " ").strip()
    worker_s = f" · {worker_display}" if worker_display else ""
    task_preview = f"• {str(task)[:60]}" if task else "—"
    icon = "▶" if status == "BUSY" else "⏸"
    return f"{icon} {status}{elapsed_s}{worker_s}\n" + task_preview


def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    _ = db, chat_id
    entries = list(load_guardrail_pipe_table("fly_commands", "help_entries"))
    block = "\n".join(f"- {cmd} — {desc}" for cmd, desc in entries)
    return f"{load_guardrail('fly_commands', 'help_header')}\n{block}"


def execute_lake_status() -> str:
    """/lake [status]: variables de lake y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _lake_ssh_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo leer conectividad: {e}"
    return "\n".join(lines)
