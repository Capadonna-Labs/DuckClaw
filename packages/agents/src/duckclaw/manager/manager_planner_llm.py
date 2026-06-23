"""LLM planner JSON contract and heuristic fallback plans."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from duckclaw.guardrails.loader import load_guardrail, load_guardrail_task_list

_log = logging.getLogger(__name__)


def _llm_plan(incoming: str) -> tuple[str, list[str]]:
    """
    Planner ligero basado en heurísticas que emula la salida estructurada esperada:
    {
      "plan_title": string,
      "tasks": [string]
    }

    Nota: en esta primera versión no se invoca un LLM explícito; se estructura
    el plan de forma determinista a partir del mensaje, dejando el contrato y
    el estado preparados para una futura integración con LLM.
    """
    text = (incoming or "").strip()
    if not text:
        return "Interacción sin contenido", []

    if text.startswith("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]"):
        return (
            load_guardrail("planner_tasks", "summarize_new_context_title"),
            list(load_guardrail_task_list("planner_tasks", "summarize_new_context_tasks")),
        )
    if text.startswith("[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"):
        return (
            load_guardrail("planner_tasks", "summarize_stored_context_title"),
            list(load_guardrail_task_list("planner_tasks", "summarize_stored_context_tasks")),
        )

    lower = text.lower()
    if "partida" in lower and ("ultima" in lower or "última" in lower or "reciente" in lower):
        title = "Consulta de Última Partida"
    elif (
        re.search(
            r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|contenido\s+de\s+la\s+tabla|"
            r"muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|registros?\s+de\s+la\s+tabla|"
            r"filas?\s+de\s+la\s+tabla|select\s+\*\s+from)\b",
            lower,
        )
        is not None
    ):
        title = "Consulta de Contenido de Tabla"
    elif re.search(
        r"\b(duckdb|base\s+de\s+datos|read_sql|registros?|datos\s+locales|tabla\s+local)\b",
        lower,
    ):
        title = "Consulta de Datos Locales"
    elif "tabla" in lower or "tablas" in lower or "schema" in lower or "esquema" in lower:
        title = "Inspección de Esquema de DB"
    elif "hora" in lower or "fecha" in lower or "hoy" in lower:
        title = "Consulta de Contexto Temporal"
    else:
        # Fallback: primeras ~5 palabras como título
        words = text.split()
        title = " ".join(words[:5]) if words else "Interacción del Usuario"

    tasks: list[str] = [f"Resolver la solicitud del usuario: {text}"]
    return title, tasks


def _truncate_plan_title_words(title: str, max_words: int = 5) -> str:
    """Recorta el título del plan a como mucho `max_words` palabras."""
    words = (title or "").strip().split()
    if not words:
        return ""
    return " ".join(words[:max_words])


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    """Parsea JSON del texto completo o del primer objeto {...} embebido."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _coerce_planner_payload(
    data: Any,
) -> tuple[str, list[str], dict[str, Any] | None, str | None]:
    """Valida el dict del LLM; lanza ValueError si no cumple el contrato."""
    if not isinstance(data, dict):
        raise ValueError("planner payload is not an object")
    title = data.get("plan_title")
    if title is None or not str(title).strip():
        raise ValueError("missing plan_title")
    tasks_raw = data.get("tasks")
    if tasks_raw is None:
        tasks_list: list[str] = []
    elif isinstance(tasks_raw, list):
        tasks_list = [str(x).strip() for x in tasks_raw if str(x).strip()]
    else:
        raise ValueError("tasks must be a list")

    merc_raw = data.get("mercenary", None)
    merc_obj: dict[str, Any] | None = None
    if merc_raw is None or merc_raw is False:
        merc_obj = None
    elif isinstance(merc_raw, dict):
        directive = str(merc_raw.get("directive") or "").strip()
        if not directive:
            raise ValueError("mercenary.directive is required when mercenary is an object")
        t_raw = merc_raw.get("timeout", 300)
        try:
            tmo = int(t_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("mercenary.timeout must be an integer") from exc
        tmo = max(1, min(tmo, 600))
        merc_obj = {"directive": directive, "timeout": tmo}
    else:
        raise ValueError("mercenary must be null, omitted, or an object")

    delegate_raw = data.get("delegate_worker_id")
    delegate_id: str | None = None
    if delegate_raw is not None and str(delegate_raw).strip():
        delegate_id = str(delegate_raw).strip()

    return str(title).strip(), tasks_list, merc_obj, delegate_id


def _llm_plan_from_model(
    llm: Any,
    incoming: str,
    planner_system_prompt: str,
    *,
    orchestrator_pool: list[str] | None = None,
) -> Optional[tuple[str, list[str], dict[str, Any] | None, str | None]]:
    """
    Invoca el LLM del Manager para obtener plan JSON.
    Con ``orchestrator_pool``, exige ``delegate_worker_id`` en la respuesta.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    append = (os.environ.get("DUCKCLAW_MANAGER_PLANNER_SYSTEM_APPEND") or "").strip()
    system_chunks = [planner_system_prompt.strip(), append]
    if orchestrator_pool:
        pool_s = ", ".join(orchestrator_pool)
        system_chunks.append(
            "Responde únicamente con JSON válido (sin markdown). Forma:\n"
            '{"plan_title": "string", "tasks": ["string", ...], '
            f'"delegate_worker_id": "uno de: {pool_s}", "mercenary": null}}'
        )
    else:
        system_chunks.append(
            "Responde únicamente con JSON válido (sin markdown). Forma:\n"
            '{"plan_title": "string", "tasks": ["string", ...], "mercenary": null | '
            '{"directive": "string", "timeout": entero_1_a_600} }'
        )
    system = "\n\n".join(c for c in system_chunks if c)
    human = f"Mensaje del usuario:\n{(incoming or '').strip()}"
    try:
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    except Exception as exc:
        _log.debug("manager planner LLM invoke failed: %s", exc)
        return None
    content: Any = getattr(resp, "content", None)
    if content is None:
        content = str(resp)
    if isinstance(content, list):
        content = "".join(
            (p.get("text", "") if isinstance(p, dict) else str(p)) for p in content
        )
    raw_text = str(content).strip()
    data = _extract_json_object(raw_text)
    if data is None:
        _log.debug("manager planner: no JSON object in model output")
        return None
    try:
        title, tasks, mercenary_spec, delegate_id = _coerce_planner_payload(data)
    except ValueError as exc:
        _log.debug("manager planner: invalid payload: %s", exc)
        return None
    title = _truncate_plan_title_words(title, 5)
    if not title:
        return None
    if not tasks:
        clip = (incoming or "").strip()[:200]
        tasks = [f"Resolver la solicitud del usuario: {clip}" if clip else "Resolver solicitud del usuario"]
    return title, tasks, mercenary_spec, delegate_id

__all__ = [
    "_coerce_planner_payload",
    "_extract_json_object",
    "_llm_plan",
    "_llm_plan_from_model",
    "_truncate_plan_title_words",
]
