"""Tools para programar revisiones proactivas /crons (reloj o intervalo)."""

from __future__ import annotations

import json
from typing import Any, List

from langchain_core.tools import StructuredTool


def _resolve_tool_db(db: Any, db_path: str) -> Any:
    if not db_path or str(getattr(db, "_path", "") or "") == db_path:
        return db
    try:
        from duckclaw import DuckClaw

        return DuckClaw(db_path, read_only=True)
    except Exception:
        return db


def register_crons_skill(tools_list: List[Any], db: Any) -> None:
    """Registra configure_crons_schedule y get_crons_schedule_status."""
    try:
        from duckclaw.forge.skills.goals_tool_context import (
            get_goals_tool_chat_id,
            get_goals_tool_db_path,
            get_goals_tool_tenant_id,
        )
        from duckclaw.graphs.on_the_fly_commands import execute_crons_schedule

        def configure_crons_schedule(command: str = "") -> str:
            """
            Programa o consulta /crons (revisiones proactivas a hora fija o intervalo).

            No confundir con configure_loop_homeostasis (/loop = auto-mejora cognitiva).
            Para recordatorios a hora exacta (ej. lunes 08:30 COT) usa --timestamp.

            command vacío → lista estado actual.
            Ejemplos:
              '--timestamp every 08:30 lun'
              '--timestamp once 2026-09-15T08:30'
              '--delta 25min --notify admin'
              '--timestamp off' · '--delta off'
              '--rm wall' · '--rm delta'
            Zona por defecto: America/Bogota (DUCKCLAW_CRONS_WALL_TZ).
            """
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"status": "error", "error": "chat_id no disponible en este turno"},
                    ensure_ascii=False,
                )
            tid = get_goals_tool_tenant_id() or "default"
            use_db = _resolve_tool_db(db, get_goals_tool_db_path())
            raw = (command or "").strip()
            try:
                message = execute_crons_schedule(
                    use_db,
                    cid,
                    raw,
                    tenant_id=tid,
                )
            except Exception as exc:  # noqa: BLE001
                return json.dumps(
                    {"status": "error", "error": str(exc)},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "status": "ok",
                    "command": raw or "(list)",
                    "message": message,
                    "hint": (
                        "Si el aviso debe mencionar una tarea concreta, crea antes una meta "
                        "con manage_homeostasis_goals (--task …). El Heartbeat dispara un "
                        "SYSTEM_EVENT en este chat a la hora programada."
                    ),
                },
                ensure_ascii=False,
            )

        def get_crons_schedule_status() -> str:
            """Lista programación /crons activa (intervalo y/o reloj) en este chat."""
            return configure_crons_schedule("")

        tools_list.append(
            StructuredTool.from_function(
                configure_crons_schedule,
                name="configure_crons_schedule",
                description=(
                    "Programa revisiones proactivas /crons en este chat: hora fija "
                    "(--timestamp every 08:30 lun | once YYYY-MM-DDTHH:MM) o intervalo "
                    "(--delta 25min). Zona America/Bogota (COT) por defecto. "
                    "command='' lista estado; '--timestamp off' / '--delta off' / '--rm wall|delta' cancelan. "
                    "NO uses configure_loop_homeostasis para recordatorios a hora exacta — eso es /loop cognitivo."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                get_crons_schedule_status,
                name="get_crons_schedule_status",
                description=(
                    "Consulta la programación /crons activa (reloj y/o intervalo) de este chat."
                ),
            )
        )
    except Exception:
        pass
