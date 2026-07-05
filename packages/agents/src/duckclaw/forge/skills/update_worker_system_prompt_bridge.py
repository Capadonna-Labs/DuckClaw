"""Tool bridge: persist system prompt updates for the active worker (self-improvement)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class UpdateMySystemPromptInput(BaseModel):
    instructions: str = Field(..., min_length=10, max_length=12000)
    mode: Literal["append", "replace"] = Field(
        default="append",
        description="append añade al prompt actual; replace lo sustituye por completo",
    )


def update_my_system_prompt(instructions: str, mode: str = "append") -> str:
    """Actualiza el system prompt del worker activo vía db-writer (DB-first)."""
    from duckclaw.commands.model_setup import _set_system_prompt_policy, get_effective_system_prompt
    from duckclaw.forge.skills.goals_tool_context import get_goals_tool_db_path, get_goals_tool_worker_id
    from duckclaw.forge.skills.knowledge_tool_context import get_session_actor_email
    from duckclaw.graphs.graph_server import get_db

    worker_id = (get_goals_tool_worker_id() or "").strip()
    db_path = (get_goals_tool_db_path() or "").strip()
    actor = (get_session_actor_email() or "").strip() or "system"
    text = (instructions or "").strip()
    write_mode = (mode or "append").strip().lower()
    if write_mode not in ("append", "replace"):
        write_mode = "append"
    if not worker_id:
        return json.dumps({"ok": False, "error": "No hay worker activo en este turno."}, ensure_ascii=False)
    if len(text) < 10:
        return json.dumps(
            {"ok": False, "error": "Las instrucciones deben tener al menos 10 caracteres."},
            ensure_ascii=False,
        )

    db = get_db(db_path) if db_path else get_db()
    try:
        current = (get_effective_system_prompt(db, worker_id) or "").strip()
        if write_mode == "replace":
            merged = text
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            block = f"\n\n---\n\n## Auto-mejora ({stamp})\n{text}"
            merged = (current + block).strip() if current else text
        ok, err = _set_system_prompt_policy(db, worker_id, merged, actor_email=actor)
        if not ok:
            return json.dumps({"ok": False, "error": err or "No se pudo persistir el prompt"}, ensure_ascii=False)
        _maybe_sync_catalog_file(db_path=db_path, worker_id=worker_id, actor=actor, content=merged)
        return json.dumps(
            {
                "ok": True,
                "worker_id": worker_id,
                "mode": write_mode,
                "chars": len(merged),
                "message": "System prompt actualizado. Los próximos turnos usarán la nueva versión.",
            },
            ensure_ascii=False,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


def _maybe_sync_catalog_file(*, db_path: str, worker_id: str, actor: str, content: str) -> None:
    if not db_path or not worker_id or not content.strip():
        return
    try:
        from duckclaw.db_write_fire_and_forget import enqueue_write_command, wait_write_task, write_poll_timeout_sec
        from duckclaw.write_commands import UpdateCatalogWorkerFileCommand

        command = UpdateCatalogWorkerFileCommand(
            tenant_id="default",
            actor_email=actor,
            worker_id=worker_id,
            file_path="system_prompt.md",
            content=content,
        )
        task_id = enqueue_write_command(command, db_path=db_path, user_id=actor)
        wait_write_task(task_id, timeout_sec=write_poll_timeout_sec())
    except Exception:
        return


def register_update_my_system_prompt_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            func=update_my_system_prompt,
            name="update_my_system_prompt",
            description=(
                "Persiste cambios en tu system prompt (auto-mejora). "
                "Usa mode=append para añadir reglas aprendidas o mode=replace para reescribirlo. "
                "Requiere instrucciones concretas (mín. 10 caracteres)."
            ),
            args_schema=UpdateMySystemPromptInput,
        )
    )
