"""
Homeostasis Bridge — registra el skill HomeostasisManager en workers con homeostasis_config.

Spec: docs/architecture/system_overview.md
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool


def register_goals_alignment_skill(
    tools_list: List[Any],
    db: Any,
) -> None:
    """Registra assess_crons_alignment (objetivos /crons vs contexto observable)."""
    try:
        from pathlib import Path

        from duckclaw.homeostasis.goals_alignment import assess_goals_alignment
        from duckclaw.forge.skills.goals_tool_context import (
            get_goals_tool_chat_id,
            get_goals_tool_db_path,
            get_goals_tool_tenant_id,
            get_goals_tool_worker_id,
        )

        def _tool_db(*, writable: bool = False) -> Any:
            path = get_goals_tool_db_path()
            base_path = str(getattr(db, "_path", "") or "")
            want_path = (path or base_path or "").strip()
            if not want_path:
                return db
            # Same handle: reuse worker DuckClaw (usually RW). Different path: open dedicated.
            same = False
            if base_path and want_path:
                try:
                    same = Path(base_path).resolve() == Path(want_path).resolve()
                except Exception:
                    same = base_path == want_path
            if same and (not writable or not bool(getattr(db, "_read_only", False))):
                return db
            try:
                from duckclaw import DuckClaw

                return DuckClaw(want_path, read_only=not writable, engine="python")
            except Exception:
                return db

        def assess_crons_alignment() -> str:
            """Mide desalineación entre manifiesto /goals y el contexto observable; devuelve JSON."""
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps(
                    {"aligned": False, "error": "chat_id no disponible en este turno"},
                    ensure_ascii=False,
                )
            tid = (get_goals_tool_tenant_id() or "").strip() or "default"
            report = assess_goals_alignment(
                _tool_db(writable=False),
                cid,
                worker_id=get_goals_tool_worker_id(),
                tenant_id=tid,
            )
            return report.to_json()

        def manage_homeostasis_goals(command: str = "") -> str:
            """
            Gestiona el manifiesto homeostasis (/goals): metas de dominio + umbrales infra.
            command vacío = listar; texto = añadir meta; 'rm <goal_id>'; 'rm all'; '--reset';
            '--set metric value'; '--monitor <goal_id>'; '--task <goal_id>'.
            Nunca llamar este tool en paralelo consigo mismo (race revive metas).
            """
            cid = get_goals_tool_chat_id()
            if not cid:
                return json.dumps({"status": "error", "error": "chat_id no disponible"}, ensure_ascii=False)
            from duckclaw.commands.goals import execute_homeostasis_goals

            tid = (get_goals_tool_tenant_id() or "").strip() or "default"
            cmd = (command or "").strip()
            needs_write = bool(cmd)  # empty = list (RO ok); any mutation needs RW
            if needs_write:
                # Short-lived RW handle: release DuckDB lock after each mutation so
                # DB-Writer can apply UPSERT_HOMEOSTASIS_MANIFEST without 24-retry storms.
                path = (get_goals_tool_db_path() or str(getattr(db, "_path", "") or "")).strip()
                if path:
                    from duckclaw import DuckClaw

                    use_db = DuckClaw(path, read_only=False, engine="python")
                    close_after = True
                else:
                    use_db = _tool_db(writable=True)
                    close_after = use_db is not db and hasattr(use_db, "close")
            else:
                use_db = _tool_db(writable=False)
                close_after = use_db is not db and hasattr(use_db, "close")
            try:
                msg = execute_homeostasis_goals(
                    use_db,
                    cid,
                    cmd,
                    tenant_id=tid,
                )
            finally:
                if close_after:
                    try:
                        use_db.close()
                    except Exception:
                        pass
            return json.dumps({"status": "ok", "message": msg}, ensure_ascii=False)

        tools_list.append(
            StructuredTool.from_function(
                assess_crons_alignment,
                name="assess_crons_alignment",
                description=(
                    "Evalúa alineación entre el manifiesto /goals y datos observables "
                    "genéricos. Devuelve JSON con aligned, items y desvíos."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                manage_homeostasis_goals,
                name="manage_homeostasis_goals",
                description=(
                    "Lista/añade/borra metas homeostasis (/goals). "
                    "command='' lista; 'rm <belief_key>' o 'rm all'; '--reset' (limpia dominio); "
                    "texto libre añade meta; '--set error_rate_pct 2' umbral infra; "
                    "'--monitor <goal_id>' revisión continua; '--task <goal_id>' tarea discreta. "
                    "CRÍTICO: no llames este tool dos veces en paralelo — serializa "
                    "(p.ej. un solo 'rm all' o un rm seguido de list en el siguiente round). "
                    "Tras rm/--reset, vuelve a listar (command='') antes de afirmar que una meta "
                    "desapareció; nunca inventes cumplimiento de metas borradas."
                ),
            )
        )
    except Exception:
        pass


def register_homeostasis_skill(
    tools_list: List[Any],
    spec: Any,
    db: Any,
    tools_by_name: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Registra la herramienta homeostasis_check en la lista de tools.
    Llamar desde factory cuando el manifest tiene homeostasis_config.
    """
    config = getattr(spec, "homeostasis_config", None)
    if not config or not isinstance(config, dict):
        return
    try:
        from duckclaw.homeostasis import BeliefRegistry, HomeostasisManager

        registry = BeliefRegistry.from_config(config)
        schema = spec.schema_name
        by_name = tools_by_name or {t.name: t for t in tools_list}

        manager = HomeostasisManager(db=db, schema=schema, registry=registry, tools_by_name=by_name)

        def homeostasis_check(belief_key: str, observed_value: float) -> str:
            """Compara un valor observado con la creencia. Devuelve Action_Plan (restore o maintain)."""
            plan = manager.check(belief_key, observed_value, auto_update=True, invoke_restoration=False)
            return json.dumps(plan, ensure_ascii=False)

        tool = StructuredTool.from_function(
            homeostasis_check,
            name="homeostasis_check",
            description=(
                "Compara un valor observado con las creencias del agente (homeostasis). "
                "Recibe belief_key (ej. monthly_metric, test_coverage) y observed_value. "
                "Devuelve Action_Plan: restore si hay anomalía, maintain si está en equilibrio."
            ),
        )
        tools_list.append(tool)
        register_goals_alignment_skill(tools_list, db)
    except Exception:
        register_goals_alignment_skill(tools_list, db)
