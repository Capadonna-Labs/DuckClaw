"""Comandos fly transversales menores: /tasks, /help, /lake, /approve, /reject."""

from __future__ import annotations

import time
from typing import Any

from duckclaw.commands.sensors import _lake_ssh_status_lines
from duckclaw.guardrails.loader import load_guardrail, load_guardrail_pipe_table


def execute_approve_reject(
    db: Any, chat_id: Any, approved: bool, args: str = "", *, tenant_id: Any = None
) -> str:
    """/approve [id] o /reject [id]: ejecuta o descarta una acción MCP pendiente de confirmación
    (p. ej. una orden de bróker) de este chat. Sin id, toma la última pendiente."""
    _ = db
    from duckclaw.forge.skills.mcp_connector_guard import take_pending

    action_id = (args or "").strip().split(" ")[0]
    try:
        action = take_pending(chat_id=str(chat_id), tenant_id=str(tenant_id or "default"), action_id=action_id)
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo leer la acción pendiente: {exc}"
    if action is None:
        return "No hay operación pendiente de aprobación en este chat (o ya venció)."
    label = f"#{action['id']} · {action['tool']}"
    if not approved:
        return f"Cancelada {label}. No se ejecutó."
    from duckclaw.forge.skills.mcp_connector_bridge import _run_async_from_sync, run_pending_action

    try:
        result = _run_async_from_sync(run_pending_action(action))
    except Exception as exc:  # noqa: BLE001
        return f"Aprobada {label}, pero falló al ejecutarse: {exc}"
    return f"Aprobada y ejecutada {label}.\n{str(result)[:3000]}"


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


def fly_help_entries() -> list[tuple[str, str]]:
    """Core /help rows plus the extension manifest's ``help_entries`` (they were parsed but never listed)."""
    entries = list(load_guardrail_pipe_table("fly_commands", "help_entries"))
    seen = {cmd.split()[0].lstrip("/").replace("_", "-").lower() for cmd, _ in entries}
    try:
        from duckclaw.extensions.manifest import load_fly_extension_manifest

        manifest = load_fly_extension_manifest()
    except Exception:
        manifest = None
    for name, desc in manifest.help_entries if manifest else ():
        if name not in seen:
            seen.add(name)
            entries.append((f"/{name}", desc))
    return entries


def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    _ = db, chat_id
    entries = fly_help_entries()
    block = "\n".join(f"- {cmd} — {desc}" for cmd, desc in entries)
    return f"{load_guardrail('fly_commands', 'help_header')}\n{block}"


def execute_lake_status() -> str:
    """/lake [status]: variables de lake y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _lake_ssh_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo leer conectividad: {e}"
    return "\n".join(lines)
