"""Deterministic planned-task shaping before worker delegation."""

from __future__ import annotations

import re
from typing import Optional

from duckclaw.guardrails.loader import format_guardrail, load_guardrail
from duckclaw.manager.manager_entry_routes import (
    _duckdb_admin_write_intent,
    _is_entry_route_system_event,
)
from duckclaw.manager.routing import _LONE_HTTP_URL_ONLY_LINE
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.workers.factory import explicit_duckdb_schema_request

def _user_demands_tool_evidence_from_db(text_lower: str) -> bool:
    """Usuario exige tools o niega persistencia (Telegram); forzar cadena SQL en _plan_task."""
    return bool(
        re.search(
            r"\b(usar?\s+(las\s+)?tools|usa(?:r)?\s+las\s+herramientas|no\s+usaste|ninguna\s+tool|ningún\s+tool|"
            r"ninguna\s+herramienta|insert(?:ar)?\s+(los\s+|la\s+)?(?:datos\s+)?en\s+la\s+(db|base)|persistencia\b|"
            r"solo\s+(?:lo\s+)?(?:está|estas|guardas)\s+en\s+memoria|solo\s+memoria|"
            r"\bread_sql\b|\badmin_sql\b|\binsert_deuda\b)\b",
            text_lower,
        )
    )


def _sanitize_manager_plan_title(
    plan_title: str | None,
    incoming: str,
    assigned_worker_id: str | None,
) -> str:
    """Evita plan_title tipo «sin herramientas» cuando el usuario exige DuckDB/tools (Planner LLM a veces alucina)."""
    if not (assigned_worker_id or "").strip():
        return (plan_title or "").strip()
    title = (plan_title or "").strip()
    if not title:
        return title
    user_tool_pressure = _user_demands_tool_evidence_from_db((incoming or "").lower())
    low = title.lower()
    bad = (
        "sin herramientas" in low
        or "without tools" in low
        or "reintentar sin" in low
        or re.search(r"\bno\s+tools\b", low) is not None
        or re.search(r"\bsin\s+tools\b", low) is not None
    )
    if not bad:
        return title
    return "Consulta y persistencia DuckDB" if user_tool_pressure else "Ejecutar con herramientas DuckDB"


def _db_tool_pressure_task(
    text: str,
    prompt_policies: PromptPolicyResolver | None,
) -> str:
    if prompt_policies is None:
        return text
    try:
        policy = prompt_policies.load("manager_task", "db_tool_pressure")
    except (FileNotFoundError, RuntimeError):
        # DB-first: sin fallback Markdown; si la policy no existe, conservar el mensaje original.
        return text
    return f"{policy}\n\n--- Mensaje del usuario ---\n{text}"

def _plan_task(
    incoming: str,
    worker_id: str,
    *,
    prompt_policies: PromptPolicyResolver | None = None,
) -> tuple[str, Optional[str]]:
    """
    Convierte el mensaje del usuario en una tarea explícita para el subagente.
    Retorna (planned_task, override_worker_id).
    override_worker_id se conserva por compatibilidad pública; el core no asigna workers por dominio.
    """
    # BOM u otros prefijos rompen startswith; el cuerpo largo no debe caer en heurísticas de tablas/Tavily.
    text = (incoming or "").strip().lstrip("\ufeff")
    if not text:
        return incoming or "", None
    if _is_entry_route_system_event(text):
        return text, None
    # Gateway (Telegram /context): el cuerpo puede mencionar DuckDB, "estructura", "schema", tablas, etc.
    # Sin este bypass, _plan_task sustituye el mensaje por TAREA: listar tablas y el worker pierde la directiva.
    if text.startswith("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]") or text.startswith(
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"
    ):
        return text, None
    if "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in text or "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in text:
        # Directiva no al inicio (p. ej. prefijo invisible): devolver el texto completo tal cual llegó al manager.
        return (incoming or "").strip(), None
    # Mensaje sólo URL: slugs pueden incluir tokens «estructura», «schema», «tablas» → falsos positivos DB.
    lone = text.strip()
    if _LONE_HTTP_URL_ONLY_LINE.match(lone):
        return lone, None
    # VLM (fotos/capturas): OCR/plantillas suelen incluir «tabla/tables/schema» sin pedir inventario DuckDB.
    # Sin bypass, _plan_task reemplazaba el mensaje por TAREA: listar tablas → worker perdía el plan del manager
    # (ej. IB «Cambios en calificaciones» → inspect_schema; logs 2026-05-11 gateway).
    if "[VLM_CONTEXT" in text and "Contexto visual adjunto:" in text:
        return (incoming or "").strip(), None
    # Briefings estructurados (macro, geopolítica, etc.): no sustituir por TAREA de listar tablas.
    if re.match(r"^##\s+\S", text):
        return text, None
    t = text.lower()
    override: Optional[str] = None
    if _duckdb_admin_write_intent(text):
        return _db_tool_pressure_task(text, prompt_policies), None
    _explicit_duckdb_schema_request = explicit_duckdb_schema_request(text)
    # BI Analyst: preguntas meta (qué puedes hacer, quién eres) → el modelo a veces ignora soul.md y copia
    # el tono genérico «Agente de Investigación Activa»; la tarea explícita lo corrige sin depender del historial.
    if (worker_id or "").strip().lower() == "bi-analyst":
        t_plain = (incoming or "").strip().lower()
        if re.search(
            r"\b(qué\s+puedes|que\s+puedes|qué\s+haces|que\s+haces|"
            r"en\s+qué\s+puedes|en\s+que\s+puedes|"
            r"qué\s+sabes\s+hacer|que\s+sabes\s+hacer|"
            r"capacidades|qué\s+ofreces|que\s+ofreces|"
            r"quién\s+eres|quien\s+eres|presentate|preséntate|"
            r"para\s+qué\s+estás|para\s+que\s+estás)\b",
            t_plain,
        ):
            return load_guardrail("manager_tasks", "bi_analyst_capabilities_question"), None
    is_db_intent = bool(
        _explicit_duckdb_schema_request
        or re.search(r"\b(db|esquema|schema|estructura|disponibles)\b", t)
        or ("nombre" in t and ("db" in t or "base" in t or "datos" in t))
    )

    # Nombre de la db / base de datos
    if re.search(r"\b(nombre\s+de\s+la\s+db|nombre\s+db|cual\s+es\s+el\s+nombre|nombre\s+de\s+la\s+base)\b", t) or (
        "nombre" in t and ("db" in t or "base" in t or "datos" in t)
    ):
        return load_guardrail("manager_tasks", "duckdb_name_query"), override
    # Contenido de una tabla concreta
    is_table_content_intent = bool(
        re.search(
            r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|"
            r"hay\s+algo\s+en\s+(la\s+)?tabla|hay\s+datos\s+en\s+(la\s+)?tabla|"
            r"contenido\s+de\s+la\s+tabla|"
            r"muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|registros?\s+de\s+la\s+tabla|"
            r"filas?\s+de\s+la\s+tabla|select\s+\*\s+from)\b",
            t,
        )
    )
    if is_table_content_intent:
        table_name: Optional[str] = None
        m_from = re.search(r"\bfrom\s+([a-zA-Z_][\w.]*)\b", t)
        if m_from:
            table_name = m_from.group(1)
        if not table_name:
            m_tabla = re.search(r"\btabla\s+([a-zA-Z_][\w.]*)\b", t)
            if m_tabla:
                table_name = m_tabla.group(1)
        if not table_name:
            m_registros = re.search(r"\bregistros?\s+de\s+([a-zA-Z_][\w.]*)\b", t)
            if m_registros:
                table_name = m_registros.group(1)

        if table_name:
            return (
                format_guardrail("manager_tasks", "table_content_named", table_name=table_name),
                override,
            )
        return load_guardrail("manager_tasks", "table_content_generic"), override

    # Tablas / esquema: mismo criterio que is_db_intent explícito (evitar «tabla» suelta en informes IB/ocr).
    if _explicit_duckdb_schema_request:
        return load_guardrail("manager_tasks", "list_database_tables"), override
    if is_db_intent and _user_demands_tool_evidence_from_db(t):
        return _db_tool_pressure_task(text, prompt_policies), override
    return text, override

__all__ = [
    "_db_tool_pressure_task",
    "_plan_task",
    "_sanitize_manager_plan_title",
    "_user_demands_tool_evidence_from_db",
]
