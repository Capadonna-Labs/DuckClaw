"""Tools para que el agente active/desactive su termostato infra meditate."""

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


def register_meditate_skill(tools_list: List[Any], db: Any) -> None:
    """Registra configure_meditate_homeostasis y get_meditate_homeostasis_status."""
    try:
        from duckclaw.forge.skills.goals_tool_context import (
            get_goals_tool_chat_id,
            get_goals_tool_db_path,
            get_goals_tool_tenant_id,
            get_goals_tool_worker_id,
        )
        from duckclaw.graphs.on_the_fly_commands import (
            apply_meditate_schedule,
            get_chat_state,
            get_meditate_schedule_status,
            parse_meditate_delta_arg,
        )

        def _effective_worker_id(use_db: Any, cid: str) -> str:
            wid = get_goals_tool_worker_id()
            if wid and wid.lower() != "manager":
                return wid
            return (get_chat_state(use_db, cid, "worker_id") or "").strip()

        def configure_meditate_homeostasis(interval: str) -> str:
            """
            Activa o desactiva el termostato infra meditate de este chat/worker.
            interval: 'off' para desactivar; '10min', '4h', '1h', etc. para activar.
            Ejecuta el primer ciclo al activar; los siguientes corren por ticker.
            """
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"status": "error", "error": "chat_id no disponible en este turno"},
                    ensure_ascii=False,
                )
            tid = get_goals_tool_tenant_id()
            use_db = _resolve_tool_db(db, get_goals_tool_db_path())
            wid = _effective_worker_id(use_db, cid)
            raw = (interval or "").strip().lower()
            if raw in ("off", "disable", "0", "false", "no"):
                applied = apply_meditate_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=0,
                    run_first_cycle=False,
                )
                return json.dumps(applied, ensure_ascii=False)
            secs, err = parse_meditate_delta_arg(raw)
            if err:
                return json.dumps({"status": "error", "error": err}, ensure_ascii=False)
            if secs == 0:
                applied = apply_meditate_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=0,
                    run_first_cycle=False,
                )
                return json.dumps(applied, ensure_ascii=False)
            applied = apply_meditate_schedule(
                use_db,
                cid,
                tenant_id=tid,
                worker_id=wid,
                interval_seconds=int(secs),
                run_first_cycle=True,
            )
            return json.dumps(applied, ensure_ascii=False)

        def get_meditate_homeostasis_status() -> str:
            """Devuelve JSON con schedule meditate y snapshot del manifiesto /goals."""
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"status": "error", "error": "chat_id no disponible"},
                    ensure_ascii=False,
                )
            tid = get_goals_tool_tenant_id()
            use_db = _resolve_tool_db(db, get_goals_tool_db_path())
            schedule = get_meditate_schedule_status(use_db, cid)
            from harness_core.targets import load_homeostasis_manifest

            manifest = load_homeostasis_manifest(use_db, tid, chat_id=cid)
            out: dict[str, Any] = {
                "status": "ok",
                **schedule,
                "manifest": manifest.model_dump(),
                "goals_count": len(manifest.goals),
            }
            if applied := schedule.get("enabled"):
                out["note"] = (
                    "Meditate contrasta métricas infra y metas del manifiesto; "
                    "define metas con manage_homeostasis_goals o /goals."
                )
            return json.dumps(out, ensure_ascii=False)

        tools_list.append(
            StructuredTool.from_function(
                configure_meditate_homeostasis,
                name="configure_meditate_homeostasis",
                description=(
                    "Activa o desactiva el termostato meditate (telemetría vs manifiesto /goals). "
                    "interval='off' o '10min'/'4h'. Programación del agente LLM: /crons --delta."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                get_meditate_homeostasis_status,
                name="get_meditate_homeostasis_status",
                description=(
                    "Consulta meditate activo, intervalo, manifiesto homeostasis y metas cargadas."
                ),
            )
        )
    except Exception:
        pass
