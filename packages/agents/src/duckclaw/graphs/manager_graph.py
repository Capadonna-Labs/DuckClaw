"""
Manager graph: orquestador que asigna cada mensaje a un subagente (worker) y registra en /tasks y /history.

State: incoming, history, chat_id, reply, assigned_worker_id, planned_task, messages (opcional).
Flujo: router -> plan (formula tarea clara para el worker) -> invoke_worker (set_busy, invoca worker, set_idle, append_task_audit).
Spec: Plan manager orquestador de subagentes.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)
_worker_graph_cache: dict[str, Any] = {}


def _plan_task(incoming: str, worker_id: str) -> tuple[str, Optional[str]]:
    """
    Convierte el mensaje del usuario en una tarea explícita para el subagente.
    Retorna (planned_task, override_worker_id).
    override_worker_id: si la intención es DB/tablas y el rol actual es personalizable, delegar a finanz si existe.
    """
    text = (incoming or "").strip()
    if not text:
        return incoming or "", None
    t = text.lower()
    override: Optional[str] = None
    # Intención DB/tablas/nombre → si el rol es personalizable, usar finanz (especialista) si está disponible
    is_db_intent = (
        re.search(r"\b(nombre\s+de\s+la\s+db|db|tablas?|tables?|esquema|schema|estructura|disponibles)\b", t)
        or "tablas" in t
        or ("nombre" in t and ("db" in t or "base" in t or "datos" in t))
    )
    if is_db_intent and (worker_id or "").strip().lower() == "personalizable":
        override = "finanz"  # invoke_worker lo usará si finanz está en list_workers

    # Nombre de la db / base de datos
    if re.search(r"\b(nombre\s+de\s+la\s+db|nombre\s+db|cual\s+es\s+el\s+nombre|nombre\s+de\s+la\s+base)\b", t) or (
        "nombre" in t and ("db" in t or "base" in t or "datos" in t)
    ):
        task = (
            "TAREA: El usuario quiere saber qué base de datos se está usando. "
            "Ejecuta get_db_path y responde de forma proactiva: indica la db usada en texto plano (sin comillas ni negrita). En el cierre invita a /team, /tasks, /help y a crear objetivos con /goals (por defecto están vacíos). Usa 1-2 emojis si encaja."
        )
        return task, override
    # Tablas / esquema / estructura
    if re.search(
        r"\b(tablas?|tables?|esquema|schema|estructura|listar\s+tablas|disponibles)\b",
        t,
    ) or "tablas" in t or "qué tablas" in t or "que tablas" in t:
        task = (
            "TAREA: El usuario quiere ver las tablas de la base de datos. "
            "Ejecuta run_sql con SHOW TABLES o SELECT desde information_schema.tables y responde con la lista de tablas. En el cierre invita a /team, /tasks, /help y a crear objetivos con /goals."
        )
        return task, override
    return text, override


def _task_summary_for_activity(incoming: str, planned_task: str) -> str:
    """Resumen corto de la tarea para /tasks (activity), no el planned_task completo."""
    t = (incoming or "").strip().lower()
    pt = (planned_task or "").strip().lower()
    # Nombre de la db
    if re.search(r"\b(nombre\s+de\s+la\s+db|nombre\s+db|cual\s+es\s+el\s+nombre|nombre\s+de\s+la\s+base)\b", t) or (
        "nombre" in t and ("db" in t or "base" in t or "datos" in t)
    ) or "get_db_path" in pt and "nombre" in pt:
        return "Buscando el nombre de la db disponible."
    # Tablas / esquema
    if re.search(
        r"\b(tablas?|tables?|esquema|schema|estructura|listar\s+tablas|disponibles)\b",
        t,
    ) or "tablas" in t or "qué tablas" in t or "que tablas" in t or "show tables" in pt:
        return "Listando tablas de la base de datos."
    # Fallback: primeras palabras del mensaje del usuario (máx. ~50 caracteres)
    if incoming and len(incoming) > 48:
        return (incoming[:48] + "…").strip()
    return incoming or "Procesando solicitud."


def build_manager_graph(
    db: Any,
    llm: Optional[Any] = None,
    *,
    templates_root: Optional[Path] = None,
    db_path: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
) -> Any:
    """
    Construye el grafo manager: router -> invoke_worker.
    db: DuckClaw para agent_config y task_audit_log.
    """
    from langgraph.graph import END, StateGraph
    from duckclaw.graphs.on_the_fly_commands import (
        get_chat_state,
        get_team_templates,
        append_task_audit,
    )
    from duckclaw.graphs.activity import set_busy, set_idle
    from duckclaw.workers.factory import build_worker_graph as _build_worker_graph
    from duckclaw.workers.factory import list_workers

    if db_path is None:
        try:
            from duckclaw.gateway_db import get_gateway_db_path
            db_path = get_gateway_db_path()
        except Exception:
            db_path = ""

    # None -> use WORKERS_TEMPLATES_DIR (forge/templates) so workers are forge/templates/<id>/
    troot = templates_root

    def router_node(state: dict) -> dict:
        """Equipo del chat (get_team_templates) o todos los templates. El manager delega según el plan. Preserva incoming/history/chat_id."""
        chat_id = state.get("chat_id") or ""
        available = get_team_templates(db, chat_id) or list_workers(troot)
        assigned = available[0] if available else None
        out = {"assigned_worker_id": assigned, "available_templates": available}
        # Preservar estado para nodos siguientes (por si el grafo hace merge sustituyendo)
        if "incoming" in state:
            out["incoming"] = state["incoming"]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        return out

    def plan_node(state: dict) -> dict:
        """Formula un plan / tarea clara y opcionalmente asigna finanz para intenciones DB/tablas."""
        # Preservar incoming por si el estado no lo propaga (fallback: input, message)
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        available_plan = state.get("available_templates") or list_workers(troot)
        default_worker = available_plan[0] if available_plan else None
        assigned = (state.get("assigned_worker_id") or default_worker or "").strip() or default_worker
        if not incoming:
            _log.warning("manager plan: incoming vacío en state (keys=%s)", list(state.keys()))
        planned, override_worker = _plan_task(incoming, assigned)
        planned_final = planned or incoming
        task_summary = _task_summary_for_activity(incoming, planned_final)
        out = {"planned_task": planned_final, "incoming": incoming, "task_summary": task_summary}
        if override_worker and override_worker in available_plan:
            out["assigned_worker_id"] = override_worker
        elif assigned not in available_plan and available_plan:
            out["assigned_worker_id"] = available_plan[0]
        out["available_templates"] = available_plan
        # Preservar estado para invoke_worker
        out["incoming"] = incoming or state.get("incoming") or state.get("input") or state.get("message") or ""
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        # Actualizar activity para /tasks con el resumen (no el planned_task completo)
        set_busy(state.get("chat_id") or "", task=task_summary, worker_id=out.get("assigned_worker_id", assigned))
        # Log del plan para PM2 / stdout
        plan_preview = (planned_final or incoming).strip()
        if len(plan_preview) > 200:
            plan_preview = plan_preview[:200] + "..."
        _log.info("manager plan: planned_task=%s", plan_preview or "(vacío)")
        return out

    def invoke_worker_node(state: dict) -> dict:
        """Invoca el grafo del worker asignado; set_busy/set_idle y append_task_audit. Solo invoca si el worker existe en templates."""
        chat_id = state.get("chat_id") or ""
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        planned_task = (state.get("planned_task") or "").strip() or incoming
        history = state.get("history") or []
        available = state.get("available_templates") or list_workers(troot)
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        if assigned not in available:
            assigned = available[0] if available else None
        if assigned is None:
            set_idle(chat_id)
            _log.warning("manager: no hay plantillas de worker disponibles en %s", getattr(troot, "__str__", lambda: "")() or "forge/templates")
            return {
                "reply": "No hay plantillas de worker configuradas. Añade al menos una en forge/templates (con manifest.yaml).",
                "messages": None,
                "_audit_done": True,
                "assigned_worker_id": None,
            }
        task_summary = (state.get("task_summary") or "").strip() or _task_summary_for_activity(incoming, planned_task)

        set_busy(chat_id, task=task_summary, worker_id=assigned)
        t0 = time.monotonic()
        reply = ""
        messages = None
        status = "SUCCESS"
        try:
            global _worker_graph_cache
            if assigned not in _worker_graph_cache:
                _worker_graph_cache[assigned] = _build_worker_graph(
                    assigned,
                    db_path,
                    llm,
                    templates_root=troot,  # None => forge/templates
                    llm_provider=llm_provider or "",
                    llm_model=llm_model or "",
                    llm_base_url=llm_base_url or "",
                )
            worker_graph = _worker_graph_cache[assigned]
            # Pasar la tarea planificada al worker para que use herramientas y no responda genérico
            worker_state = {"incoming": planned_task, "history": history}
            result = worker_graph.invoke(worker_state)
            reply = str(result.get("reply") or result.get("output") or "Sin respuesta.")
            messages = result.get("messages")
            # Log tool use para PM2 (tras manager plan)
            _tool_names = []
            for m in (messages or []):
                for tc in (getattr(m, "tool_calls", None) or []):
                    if isinstance(tc, dict) and tc.get("name"):
                        _tool_names.append(tc["name"])
                n = getattr(m, "name", None)
                if n:
                    _tool_names.append(n)
            _tools_list = list(dict.fromkeys(_tool_names))
            _log.info(
                "manager tool_use: delegó a worker=%s | tools usadas=%s",
                assigned,
                _tools_list if _tools_list else "ninguna",
            )
        except Exception as e:
            reply = str(e)[:2048]
            status = "FAILED"
        finally:
            set_idle(chat_id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            append_task_audit(db, chat_id, assigned, incoming, status, elapsed_ms)

        # El manager ya registró en task_audit_log; el Gateway no debe duplicar.
        # assigned_worker_id para que el Gateway lo use en respuesta y trazas.
        return {
            "reply": reply,
            "messages": messages,
            "_audit_done": True,
            "assigned_worker_id": assigned,
        }

    graph = StateGraph(dict)
    graph.add_node("router", router_node)
    graph.add_node("plan", plan_node)
    graph.add_node("invoke_worker", invoke_worker_node)
    graph.set_entry_point("router")
    graph.add_edge("router", "plan")
    graph.add_edge("plan", "invoke_worker")
    graph.add_edge("invoke_worker", END)
    return graph.compile()
