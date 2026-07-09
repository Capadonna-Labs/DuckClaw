"""Tools para programar auto-mejora cognitiva /loop."""

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


def register_loop_skill(tools_list: List[Any], db: Any) -> None:
    """Registra configure_loop_homeostasis y get_loop_homeostasis_status."""
    try:
        from duckclaw.forge.skills.goals_tool_context import (
            get_goals_tool_chat_id,
            get_goals_tool_db_path,
            get_goals_tool_tenant_id,
            get_goals_tool_worker_id,
        )
        from duckclaw.graphs.on_the_fly_commands import (
            apply_loop_idle_schedule,
            apply_loop_schedule,
            get_chat_state,
            get_loop_schedule_status,
            parse_loop_delta_arg,
        )

        def _effective_worker_id(use_db: Any, cid: str) -> str:
            wid = get_goals_tool_worker_id()
            if wid and wid.lower() != "manager":
                return wid
            return (get_chat_state(use_db, cid, "worker_id") or "").strip()

        def configure_loop_homeostasis(interval: str, mode: str = "clock") -> str:
            """
            Activa o desactiva la programación /loop de este chat/worker.
            interval: 'off' para desactivar; '10min', '4h', '1h', etc. para activar.
            mode: 'clock' (reloj Heartbeat) o 'idle' (silencio desde último mensaje).
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
            schedule_mode = (mode or "clock").strip().lower()
            if raw.startswith("idle:"):
                schedule_mode = "idle"
                raw = raw.split(":", 1)[1].strip()
            if raw in ("off", "disable", "0", "false", "no"):
                applied = apply_loop_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=0,
                )
                return json.dumps(applied, ensure_ascii=False)
            secs, err = parse_loop_delta_arg(raw)
            if err:
                return json.dumps({"status": "error", "error": err}, ensure_ascii=False)
            if secs == 0:
                applied = apply_loop_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=0,
                )
                return json.dumps(applied, ensure_ascii=False)
            if schedule_mode == "idle":
                applied = apply_loop_idle_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=int(secs),
                )
            else:
                applied = apply_loop_schedule(
                    use_db,
                    cid,
                    tenant_id=tid,
                    worker_id=wid,
                    interval_seconds=int(secs),
                )
            return json.dumps(applied, ensure_ascii=False)

        def get_loop_homeostasis_status() -> str:
            """Devuelve JSON con schedule meditate y snapshot del manifiesto /goals."""
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"status": "error", "error": "chat_id no disponible"},
                    ensure_ascii=False,
                )
            tid = get_goals_tool_tenant_id()
            use_db = _resolve_tool_db(db, get_goals_tool_db_path())
            schedule = get_loop_schedule_status(use_db, cid)
            from harness_core.targets import load_homeostasis_manifest

            manifest = load_homeostasis_manifest(use_db, tid, chat_id=cid)
            out: dict[str, Any] = {
                "status": "ok",
                **schedule,
                "manifest": manifest.model_dump(),
                "goals_count": len(manifest.goals),
            }
            if schedule.get("enabled"):
                out["note"] = (
                    "Meditate programa auto-mejora cognitiva vs manifiesto /goals; "
                    "define metas con manage_homeostasis_goals o /goals."
                )
            try:
                from duckclaw.hitl.loop_validation_service import get_pending_validation

                pending = get_pending_validation(use_db, cid)
                if pending:
                    out["hitl_pending"] = {
                        "validation_id": pending.get("validation_id"),
                        "status": pending.get("status"),
                    }
            except Exception:
                pass
            return json.dumps(out, ensure_ascii=False)

        def request_homeostasis_validation(
            goals_summary: str,
            metrics_json: str = "{}",
            deviations_json: str = "{}",
        ) -> str:
            """
            Solicita validación HITL antes de declarar homeostasis.
            Llamar solo cuando métricas alineadas (sin desviaciones).
            """
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"status": "error", "error": "chat_id no disponible en este turno"},
                    ensure_ascii=False,
                )
            tid = get_goals_tool_tenant_id() or "default"
            use_db = _resolve_tool_db(db, get_goals_tool_db_path())
            try:
                metrics = json.loads(metrics_json or "{}")
                if not isinstance(metrics, dict):
                    metrics = {}
            except Exception:
                metrics = {}
            try:
                deviations = json.loads(deviations_json or "{}")
                if not isinstance(deviations, dict):
                    deviations = {}
            except Exception:
                deviations = {}
            if deviations:
                return json.dumps(
                    {
                        "status": "error",
                        "error": "deviations_present",
                        "message": "Hay desviaciones; no solicites HITL hasta corregirlas.",
                    },
                    ensure_ascii=False,
                )
            try:
                from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts
                from duckclaw.homeostasis.goals_alignment import hitl_declarable_for_goals

                manifest = load_homeostasis_manifest(use_db, tid, chat_id=cid)
                declarable, note = hitl_declarable_for_goals(manifest_goals_as_dicts(manifest))
                if not declarable:
                    return json.dumps(
                        {
                            "status": "error",
                            "error": "monitor_goals_not_declarable",
                            "message": note,
                        },
                        ensure_ascii=False,
                    )
            except Exception:
                pass
            from duckclaw.hitl.loop_validation_service import (
                create_pending_validation,
                format_hitl_user_prompt,
            )

            snapshot = {
                "goals_summary": (goals_summary or "").strip(),
                "current_metrics": metrics,
                "deviations": deviations,
            }
            created = create_pending_validation(
                use_db,
                cid,
                tenant_id=tid,
                snapshot=snapshot,
                goals_summary=(goals_summary or "").strip(),
            )
            if not created.get("ok"):
                existing_id = created.get("validation_id") or ""
                err = created.get("error") or ""
                msg = created.get("message") or (
                    "Ya hay validación HITL pendiente. "
                    f"Usa /loop-approve {existing_id} o /loop-reject."
                    if err == "pending_validation_exists"
                    else f"No se pudo crear validación HITL: {err}"
                )
                return json.dumps(
                    {
                        "status": "error",
                        "error": err,
                        "validation_id": existing_id,
                        "message": msg,
                    },
                    ensure_ascii=False,
                )
            vid = str(created.get("validation_id") or "")
            user_prompt = format_hitl_user_prompt(vid, goals_summary)
            return json.dumps(
                {
                    "status": "pending_hitl",
                    "validation_id": vid,
                    "user_prompt": user_prompt,
                    "note": (
                        "homeostasis_achieved en evaluate_homeostasis solo indica métricas "
                        "alineadas; no declares homeostasis hasta /loop-approve."
                    ),
                },
                ensure_ascii=False,
            )

        tools_list.append(
            StructuredTool.from_function(
                configure_loop_homeostasis,
                name="configure_loop_homeostasis",
                description=(
                    "Programa auto-mejora /loop (evalúa /goals periódicamente). "
                    "interval='off' o '10min'/'4h'. mode='clock' (reloj) o 'idle' (silencio desde último mensaje). "
                    "Revisión ligera al usuario: /crons --delta."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                get_loop_homeostasis_status,
                name="get_loop_homeostasis_status",
                description=(
                    "Consulta meditate activo, intervalo, manifiesto homeostasis y metas cargadas."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                request_homeostasis_validation,
                name="request_homeostasis_validation",
                description=(
                    "Paso HITL final de /loop solo para metas **task** (sin metas monitor en manifiesto). "
                    "Metas monitor (métricas continuas como latencia o error_rate) se revisan cada ciclo y **nunca** se declaran cumplidas. "
                    "Solo si no hay desviaciones. Detente tras llamar; homeostasis solo tras /loop-approve."
                ),
            )
        )
    except Exception:
        pass
