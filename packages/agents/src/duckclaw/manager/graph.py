"""
Manager graph: orquestador que asigna cada mensaje a un subagente (worker) y registra en /tasks y /history.

State: incoming, history, chat_id, reply, assigned_worker_id, planned_task, messages (opcional).
Flujo: router -> plan (formula tarea clara para el worker) -> invoke_worker (set_busy, invoca worker, set_idle, append_task_audit).
Spec: Plan manager orquestador de subagentes.

Las etiquetas de log ``{worker} {n}`` tras delegación son **subagent_slot_rank** (Redis), no IDs de réplica PM2;
ver ``duckclaw.graphs.subagent_run_id``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from duckclaw.graphs.state import ManagerAgentState
from duckclaw.graphs.sandbox import extract_latest_sandbox_figure_base64
from duckclaw.graphs.subagent_run_id import acquire_subagent_slot, release_subagent_slot
from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_plan, log_sys, set_log_context

from duckclaw.guardrails.loader import format_guardrail, load_guardrail, load_guardrail_task_list
from duckclaw.manager.routing import (
    _LONE_HTTP_URL_ONLY_LINE,
    _worker_id_alnum_slug,
    _worker_matches_id,
)
from duckclaw.manager.fast_plans import (
    _manager_visual_generation_intent,
    _try_capability_fast_plan,
)
from duckclaw.manager.fast_replies import (
    _capabilities_fast_reply_text,
    _greeting_fast_reply_text,
    _manager_capabilities_fast_path_ok,
    _manager_greeting_fast_path_ok,
)
from duckclaw.manager.task_classification import (
    _incoming_has_context_summary_system_directive,
    _incoming_looks_like_semantic_context_followup,
    _worker_should_use_lite_stdio_mcp_surface,
)
from duckclaw.manager.resilience_flow import (
    _initial_replan_state,
    _planned_task_with_replan_suffix,
    _replan_output_fields,
)
from duckclaw.manager.task_activity import (
    _activity_task_for_plan,
    _append_task_audit_safely,
    _is_ai_like_message,
    _message_body_text_for_embedded_tool,
    _messages_turn_for_tool_audit,
    _task_summary_for_activity,
    _tool_name_from_embedded_json_content,
    _worker_tool_names_from_messages,
)
from duckclaw.manager.worker_reply_formatting import (
    _prepend_subagent_label_once,
    _reply_already_has_worker_header,
    _strip_leading_subagent_instance_headers,
    _worker_base_from_subagent_label,
)
from duckclaw.forge.rag.context_blocks import preserve_context_blocks_for_worker
from duckclaw.workers.factory import explicit_duckdb_schema_request
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.graphs.agent_resilience import (
    classify_exception_for_replan,
    format_exhausted_plan_failure,
    merge_failure_reasons,
    replan_enabled,
    worker_reply_suggests_replan_without_tools,
)

_log = logging.getLogger(__name__)
_obs = get_obs_logger()
_worker_graph_cache: dict[str, Any] = {}
_vault_invoke_guard = threading.Lock()
_vault_invoke_locks: dict[str, threading.Lock] = {}


def _load_manager_task_policy(
    prompt_policies: PromptPolicyResolver | None,
    policy_name: str,
    **kwargs: str,
) -> str | None:
    """Resuelve manager_task desde DuckDB sin fallback Markdown."""
    if prompt_policies is None:
        return None
    try:
        if kwargs:
            return prompt_policies.format("manager_task", policy_name, **kwargs)
        return prompt_policies.load("manager_task", policy_name)
    except (FileNotFoundError, RuntimeError):
        return None


def _vault_lock_key(path: str) -> str:
    p = (path or "").strip()
    if not p or p == ":memory:":
        return ""
    try:
        return str(Path(p).expanduser().resolve())
    except Exception:
        return str(Path(p).expanduser())


def worker_graph_cache_entry_count() -> int:
    """Cuántos grafos de worker hay en caché (tests / diagnóstico / comandos fly)."""
    return len(_worker_graph_cache)


def _release_worker_db_handle(worker_graph: Any | None, *, cache_key: str = "") -> bool:
    """
    Cierra ``_worker_db`` del grafo cacheado y opcionalmente lo saca de la caché.

    Debe llamarse en cuanto termina ``worker_graph.invoke`` si el worker abrió RW en el
    mismo .duckdb que el manager y usa herramientas RW: dejar el handle abierto hasta el
    ``finally`` del nodo bloquea db-writer y provoca «different configuration» al reabrir RO.
    """
    global _worker_graph_cache
    if worker_graph is None:
        return False
    wdb = getattr(worker_graph, "_worker_db", None)
    if wdb is None:
        return False
    _path_hint = str(getattr(wdb, "_path", "") or "")[-96:]
    _ro = bool(getattr(wdb, "_read_only", False))
    try:
        wdb.close()
    except Exception:
        pass
    if cache_key:
        try:
            _worker_graph_cache.pop(cache_key, None)
        except Exception:
            pass
    return True


def clear_worker_graph_cache() -> None:
    """
    Los grafos de worker cierran sobre un DuckClaw concreto; tras cerrar la conexión del manager
    hay que vaciar la caché para no reutilizar handles muertos en la siguiente petición.

    Cierra explícitamente ``_worker_db`` en cada grafo cacheado antes de vaciar: DuckDB no permite
    dos conexiones al mismo archivo con configuración distinta (p. ej. RW del worker + nuevo RW
    para /model, /team en fly).
    """
    global _worker_graph_cache
    for _g in list(_worker_graph_cache.values()):
        wdb = getattr(_g, "_worker_db", None)
        if wdb is not None:
            try:
                wdb.close()
            except Exception:
                pass
    _worker_graph_cache.clear()


def _agent_config_db_for_vault(hub_db: Any, vault_db_path: str | None) -> Any:
    """
    Lee claves por chat (team_templates, sandbox_enabled, llm_*) desde el vault del tenant
    cuando existe; si no, desde el hub ``hub_db``. Evita mezclar equipos del hub multiplex
    con rutas que comparten chat_id pero usan otro .duckdb.

    Si vault y hub son el mismo archivo, reutilizar ``hub_db``: ``GatewayDbEphemeralReadonly``
    abre RO efímero y choca con el handle RW del manager en perfil Spawn (mismo PID).
    """
    vp = (vault_db_path or "").strip()
    if vp and vp != ":memory:":
        hub_path = str(getattr(hub_db, "_path", "") or "").strip()
        if hub_path:
            from duckclaw.workers.factory import _same_duckdb_file

            if _same_duckdb_file(hub_path, vp):
                return hub_db
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly

        return GatewayDbEphemeralReadonly(vp)
    return hub_db


def _worker_should_use_url_research_mcp_surface(text: str) -> bool:
    """
    Mensaje solo URL (HTTPS): omite GitHub/Trends/Reddit en cold start del grafo worker.
    Reddit MCP solo si la URL es reddit.com (``incoming_hint`` en build_worker_graph).
    """
    inc = (text or "").strip()
    if not _LONE_HTTP_URL_ONLY_LINE.match(inc):
        return False
    return not _manager_visual_generation_intent(inc)


def _duckdb_admin_write_intent(text: str) -> bool:
    """
  Mutaciones DuckDB (admin_sql / DDL) requieren un worker con política RW resuelta fuera del core.
  """
    t = (text or "").strip().lower()
    if not t:
        return False
    if re.search(r"\badmin_sql\b", t):
        return True
    if re.search(
        r"\b(create\s+table|alter\s+table|drop\s+table|truncate\s+table|"
        r"insert\s+into|delete\s+from)\b",
        t,
    ):
        return True
    if re.search(r"\bupdate\s+[a-z_][\w.]*\b", t):
        return True
    if re.search(
        r"\b(insert_deuda|insert_transaction|insert_cuenta|insert_presupuesto)\b",
        t,
    ):
        return True
    return False

def _strip_mercenary_spec_for_browser_worker(
    out: dict[str, Any], templates_root: Path | None = None, db: Any = None
) -> bool:
    """
    Workers con ``browser_sandbox`` en manifest usan ``run_browser_sandbox`` (Playwright), no mercenario stub.
    Devuelve True si se eliminó ``mercenary_spec`` del estado del plan.
    """
    wid = (out.get("assigned_worker_id") or "").strip()
    if not out.get("mercenary_spec") or not wid:
        return False
    try:
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(wid, templates_root, db=db, tenant_id="default")
        if not getattr(spec, "browser_sandbox", False):
            return False
    except Exception:
        return False
    out.pop("mercenary_spec", None)
    return True


def _should_disable_mercenary_for_admin_ui(chat_id: str | None) -> bool:
    """Consola admin / playground: nunca mercenario stub; delegar al worker con Strix browser."""
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        return bool(is_admin_ui_chat_session(chat_id))
    except Exception:
        cid = (chat_id or "").strip()
        return cid.startswith(("admin-conv-", "admin-section-", "admin-ui")) or cid == "admin-playground"


_BROWSER_MERCENARY_INTENT_MARKERS = (
    "run_browser_sandbox",
    "playwright",
    "novnc",
    "no vnc",
    "browser sandbox",
    "computer use",
    "abrir ",
    "abre ",
    "navega",
    "navegar",
    "página web",
    "pagina web",
    "sitio web",
    "http://",
    "https://",
    "sandbox para",
    "usa sandbox",
    "usar sandbox",
    "el colombiano",
    "elcolombiano",
)


def _should_disable_mercenary_for_browser_intent(
    incoming: str,
    tasks: list[str] | None,
    plan_title: str | None,
    *,
    chat_id: str | None = None,
) -> bool:
    """
    Planes de navegación / computer use deben ir al worker (run_browser_sandbox), no al stub mercenario.
    """
    if _should_disable_mercenary_for_admin_ui(chat_id):
        return True
    blob = " ".join(
        [
            incoming or "",
            plan_title or "",
            " ".join(str(t) for t in (tasks or []) if t),
        ]
    )
    if not blob.strip():
        return False
    low = blob.lower()
    return any(m in low for m in _BROWSER_MERCENARY_INTENT_MARKERS)


def _is_goals_proactive_system_event(text: str) -> bool:
    """True si el mensaje es el SYSTEM_EVENT del ticker de /crons --delta (legado /goals; misma ruta HTTP)."""
    t = (text or "").strip()
    return t.startswith("[SYSTEM_EVENT:") and proactive_review_event_phrase_in_text(t)


def _is_entry_route_system_event(text: str) -> bool:
    """
    True si el inbound debe ejecutarse en ``entry_worker_id`` (worker de la ruta HTTP),
    sin que el manager lo reasigne (p. ej. eventos de ruta explícita hacia el worker de entrada).
    """
    t = (text or "").strip()
    if _is_goals_proactive_system_event(t):
        return True
    if not t.startswith("[SYSTEM_EVENT:"):
        return False
    return '"type":"TRADING_TICK"' in t or '"type": "TRADING_TICK"' in t


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
    elif "saldo" in lower or "dinero" in lower or "cuenta" in lower:
        title = "Consulta de Saldo Total"
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


def _load_orchestrator_planner_prompt(coordinator_id: str, templates_root: Any) -> str:
    from duckclaw.workers.manifest import get_worker_dir

    path = get_worker_dir(coordinator_id, templates_root) / "orchestrator_planner.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return (
        "Eres el planner del coordinador AXIS. Elige delegate_worker_id de la lista permitida "
        "y redacta tasks para ese subagente."
    )


def _resolve_orchestrator_delegate(
    incoming: str,
    pool: list[str],
    coordinator_id: str,
    llm: Any | None,
    planner_system_prompt: str,
    templates_root: Any,
) -> str:
    from duckclaw.workers.orchestrator import pick_delegate_from_planner, pick_delegate_heuristic

    delegate: str | None = None
    if llm is not None:
        orch_prompt = _load_orchestrator_planner_prompt(coordinator_id, templates_root)
        combined = (planner_system_prompt or "").strip()
        if combined:
            combined = f"{combined}\n\n{orch_prompt}"
        else:
            combined = orch_prompt
        parsed = _llm_plan_from_model(
            llm, incoming, combined, orchestrator_pool=list(pool) + [coordinator_id]
        )
        if parsed:
            _, _, _, delegate_id = parsed
            delegate = pick_delegate_from_planner(delegate_id, list(pool) + [coordinator_id], templates_root)
    if not delegate:
        delegate = pick_delegate_heuristic(incoming, list(pool) + [coordinator_id], coordinator_id=coordinator_id)
    return delegate or coordinator_id


def build_manager_graph(
    db: Any,
    llm: Optional[Any] = None,
    *,
    templates_root: Optional[Path] = None,
    db_path: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    planner_system_prompt: str = "",
) -> Any:
    """
    Construye el grafo manager: router -> invoke_worker.
    db: DuckClaw para agent_config y task_audit_log.
    """
    from langgraph.graph import END, StateGraph
    from duckclaw.graphs.on_the_fly_commands import (
        get_chat_state,
        get_effective_team_templates,
        append_task_audit,
        _resolve_template_id,
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
        """Equipo efectivo: chat > tenant > env > todos. El manager delega según el plan. Preserva incoming/history/chat_id."""
        chat_id = state.get("chat_id") or ""
        tenant_id = state.get("tenant_id") or "default"
        vault_path = (state.get("vault_db_path") or "").strip()
        state_db = _agent_config_db_for_vault(db, vault_path or None)
        available = list(get_effective_team_templates(state_db, chat_id, tenant_id, troot))
        preferred = (os.environ.get("DUCKCLAW_DEFAULT_WORKER_ID") or "").strip()
        assigned = available[0] if available else None
        if preferred and available:
            for wid in available:
                if (wid or "").strip().lower() == preferred.lower():
                    assigned = (wid or "").strip()
                    break
        incoming_r = (state.get("incoming") or state.get("input") or "").strip()
        entry_r = (state.get("entry_worker_id") or "").strip()
        _entry_route_ev = _is_entry_route_system_event(incoming_r)
        _all_disk_r = list_workers(troot, db=db, tenant_id=tenant_id)
        # Multiplex Telegram: si hay ruta HTTP, priorizar siempre el worker de entrada.
        _canon_entry = _resolve_template_id(_all_disk_r, entry_r) if entry_r else None
        coordinator_id: str | None = None
        delegation_pool: list[str] = []
        from duckclaw.workers.orchestrator import effective_delegation_pool, load_orchestrator_config

        orch_cfg = load_orchestrator_config(_canon_entry, troot) if _canon_entry else None
        if orch_cfg:
            coordinator_id = orch_cfg.coordinator_id
            delegation_pool = effective_delegation_pool(
                orch_cfg.orchestrates, available, troot
            )
            if coordinator_id not in delegation_pool:
                delegation_pool = [coordinator_id] + delegation_pool
            assigned = coordinator_id
            available = list(delegation_pool)
        elif _canon_entry:
            if _canon_entry not in available:
                available = list(available) + [_canon_entry]
            available = [_canon_entry] + [w for w in available if w != _canon_entry]
            assigned = _canon_entry
        out: dict[str, Any] = {"assigned_worker_id": assigned, "available_templates": available}
        if coordinator_id:
            out["coordinator_worker_id"] = coordinator_id
            out["delegation_pool"] = delegation_pool
        # Preservar estado para nodos siguientes (por si el grafo hace merge sustituyendo)
        if "incoming" in state:
            out["incoming"] = state["incoming"]
        if "input" in state:
            out["input"] = state["input"]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        _ot = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot:
            out["outbound_telegram_bot_token"] = _ot
        out.update(_initial_replan_state())
        return out

    def greeting_shortcut_node(state: ManagerAgentState) -> ManagerAgentState:
        """Responde saludos o preguntas «qué puedes hacer» sin plan ni invoke_worker."""
        chat_id = state.get("chat_id") or ""
        tenant_id = (state.get("tenant_id") or "default").strip() or "default"
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        _cid = (chat_id or "").strip() or "unknown"
        set_log_context(
            tenant_id=tenant_id,
            worker_id="manager",
            chat_id=format_chat_log_identity(_cid, state.get("username")),
        )
        coord = (state.get("coordinator_worker_id") or "").strip() or None
        pool = list(state.get("delegation_pool") or [])
        if _manager_capabilities_fast_path_ok(incoming):
            log_sys(_obs, "Capacidades: respuesta directa (sin plan ni subagente)")
            _vault_path_reply = (state.get("vault_db_path") or "").strip()
            _reply_policy_db = _agent_config_db_for_vault(db, _vault_path_reply or None)
            reply = _capabilities_fast_reply_text(
                assigned,
                coordinator_id=coord,
                delegation_pool=pool,
                prompt_policies=PromptPolicyResolver(_reply_policy_db),
            )
            _audit_title = "Capacidades (respuesta directa)"
        else:
            log_sys(_obs, "Saludo: respuesta directa (sin plan ni subagente)")
            reply = _greeting_fast_reply_text(assigned)
            _audit_title = "Saludo directo"
        _append_task_audit_safely(
            append_task_audit,
            db=db,
            chat_id=chat_id,
            worker_id=assigned or "manager",
            incoming=incoming,
            status="SUCCESS",
            elapsed_ms=0,
            plan_title=_audit_title,
        )
        out: ManagerAgentState = {
            "reply": reply,
            "_audit_done": True,
            "assigned_worker_id": assigned,
            "plan_title": None,
            "incoming": incoming,
            "input": incoming,
        }  # type: ignore[assignment]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        if "available_templates" in state:
            out["available_templates"] = state["available_templates"]
        if state.get("coordinator_worker_id"):
            out["coordinator_worker_id"] = state.get("coordinator_worker_id")
        if state.get("delegation_pool"):
            out["delegation_pool"] = state.get("delegation_pool")
        _ot_g = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_g:
            out["outbound_telegram_bot_token"] = _ot_g
        return out

    def plan_node(state: ManagerAgentState) -> ManagerAgentState:
        """Formula un plan/tarea clara, genera plan_title/tasks y conserva la ruta de catálogo."""
        _tid = (state.get("tenant_id") or "default").strip() or "default"
        _cid = (state.get("chat_id") or "").strip() or "unknown"
        set_log_context(
            tenant_id=_tid,
            worker_id="manager",
            chat_id=format_chat_log_identity(_cid, state.get("username")),
        )
        # Preservar incoming por si el estado no lo propaga (fallback: input, message)
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        available_plan = state.get("available_templates") or list_workers(troot, db=db, tenant_id=_tid)
        default_worker = available_plan[0] if available_plan else None
        assigned = (state.get("assigned_worker_id") or default_worker or "").strip() or default_worker
        coordinator_id = (state.get("coordinator_worker_id") or "").strip() or None
        delegation_pool = [str(x).strip() for x in (state.get("delegation_pool") or []) if str(x).strip()]
        if not incoming:
            _log.warning("manager plan: incoming vacío en state (keys=%s)", list(state.keys()))

        _vault_path_plan = (state.get("vault_db_path") or "").strip()
        _plan_cfg_db = _agent_config_db_for_vault(db, _vault_path_plan or None)
        _plan_prompt_policies = PromptPolicyResolver(_plan_cfg_db)
        _orch_affirm: tuple[str, list[str], str, str] | None = None
        _capability_fast: tuple[str, list[str], str, str] | None = None
        if incoming:
            try:
                from duckclaw.workers.manifest import load_manifest
                from duckclaw.workers.tool_orchestration import try_manifest_affirm_followup

                _spec_affirm = load_manifest(assigned, troot)
                _orch_affirm = try_manifest_affirm_followup(
                    incoming,
                    state.get("history"),
                    assigned,
                    _spec_affirm,
                )
            except Exception:
                _orch_affirm = None
        if incoming and not _orch_affirm:
            _capability_fast = _try_capability_fast_plan(
                incoming,
                [str(x) for x in (available_plan or []) if x],
                db=_plan_cfg_db,
                tenant_id=_tid,
            )
        if _orch_affirm:
            plan_title, tasks, _inject_orch, _ov_orch = _orch_affirm
            mercenary_spec = None
        elif _capability_fast:
            plan_title, tasks, _inject_fast, _ov_fast = _capability_fast
            mercenary_spec = None
        else:
            _psp = (planner_system_prompt or "").strip()
            mercenary_spec = None
            if _incoming_has_context_summary_system_directive(incoming):
                plan_title, tasks = _llm_plan(incoming)
            elif llm is not None and _psp:
                _parsed = _llm_plan_from_model(llm, incoming, _psp)
                if _parsed:
                    plan_title, tasks, mercenary_spec, _delegate_unused = _parsed
                else:
                    plan_title, tasks = _llm_plan(incoming)
                    mercenary_spec = None
            else:
                plan_title, tasks = _llm_plan(incoming)

            plan_title = _sanitize_manager_plan_title(plan_title, incoming, assigned)

        _plan_chat_id = (state.get("chat_id") or "").strip() or None
        if mercenary_spec is not None and _should_disable_mercenary_for_browser_intent(
            incoming, tasks, plan_title, chat_id=_plan_chat_id
        ):
            mercenary_spec = None

        override_worker: Optional[str] = None
        # Mantener lógica existente de ruteo / planned_task
        if _orch_affirm:
            if _ov_orch and _ov_orch in (available_plan or []):
                assigned = _ov_orch
            override_worker = _ov_orch
            planned = _inject_orch
            planned_final = _inject_orch
        elif _visual_fast:
            if _ov_vis and _ov_vis in (available_plan or []):
                assigned = _ov_vis
            override_worker = _ov_vis
            planned = _inject_vis
            planned_final = _inject_vis
        else:
            planned, override_worker = _plan_task(
                incoming,
                assigned,
                prompt_policies=_plan_prompt_policies,
            )
            planned_final = planned or incoming
        _pa_plan = int(state.get("plan_attempt_index") or 0)
        _max_plan = int(state.get("plan_max_attempts") or _initial_replan_state()["plan_max_attempts"])
        planned_final = _planned_task_with_replan_suffix(planned_final, _pa_plan, _max_plan)

        if coordinator_id and delegation_pool and not _orch_affirm and not _visual_fast:
            assigned = _resolve_orchestrator_delegate(
                incoming,
                delegation_pool,
                coordinator_id,
                llm,
                (planner_system_prompt or "").strip(),
                troot,
            )
            _coord_prefix = f"[Coordinado por {coordinator_id}] "
            if not (planned_final or "").strip().startswith(_coord_prefix):
                planned_final = _coord_prefix + (planned_final or incoming).strip()
            log_sys(
                _obs,
                "AXIS coordinador %s → delegado %s",
                coordinator_id,
                assigned,
            )

        # Derivar task_summary a partir del mensaje original / planned_task
        task_summary = _task_summary_for_activity(incoming, planned_final)

        user_incoming = (state.get("user_incoming") or incoming or "").strip()

        out: ManagerAgentState = {
            "planned_task": planned_final,
            "incoming": incoming,
            "user_incoming": user_incoming,
            "task_summary": task_summary,
            "plan_title": plan_title or None,
            "tasks": tasks or [],
            "replan_requested": False,
        }  # type: ignore[assignment]
        if mercenary_spec:
            out["mercenary_spec"] = mercenary_spec
        if isinstance(state.get("handoff_context"), dict):
            out["handoff_context"] = state.get("handoff_context")
        if isinstance(state.get("active_mission"), dict):
            out["active_mission"] = state.get("active_mission")

        if coordinator_id and delegation_pool:
            out["coordinator_worker_id"] = coordinator_id
            out["delegation_pool"] = delegation_pool
            if assigned:
                out["assigned_worker_id"] = assigned
        elif override_worker and override_worker in available_plan:
            out["assigned_worker_id"] = override_worker
        elif assigned not in available_plan and available_plan:
            out["assigned_worker_id"] = available_plan[0]
        else:
            out["assigned_worker_id"] = assigned

        route_entry = (state.get("entry_worker_id") or "").strip()
        if route_entry and _is_entry_route_system_event(incoming):
            _all_plan_disk = list_workers(troot, db=db, tenant_id=_tid)
            _canon_re = _resolve_template_id(_all_plan_disk, route_entry)
            if _canon_re and _canon_re in _all_plan_disk:
                out["assigned_worker_id"] = _canon_re
                if _canon_re not in available_plan:
                    available_plan = list(available_plan) + [_canon_re]
        elif route_entry:
            _all_plan_disk = list_workers(troot, db=db, tenant_id=_tid)
            _canon_play = _resolve_template_id(_all_plan_disk, route_entry)
            if _canon_play and _canon_play in _all_plan_disk:
                out["assigned_worker_id"] = _canon_play
                if _canon_play not in available_plan:
                    available_plan = list(available_plan) + [_canon_play]

        if _strip_mercenary_spec_for_browser_worker(out, troot):
            mercenary_spec = None

        out["available_templates"] = available_plan
        # Preservar estado para invoke_worker
        out["incoming"] = incoming or state.get("incoming") or state.get("input") or state.get("message") or ""
        out["input"] = out["incoming"]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        _ot_p = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_p:
            out["outbound_telegram_bot_token"] = _ot_p
        if "active_mission" in state and not out.get("active_mission"):
            out["active_mission"] = state.get("active_mission")
        # Actualizar activity para /tasks usando solo el título del plan cuando esté disponible
        activity_task = _activity_task_for_plan(plan_title, task_summary)
        set_busy(state.get("chat_id") or "", task=activity_task, worker_id=out.get("assigned_worker_id", assigned))

        # Log del plan para PM2 / stdout: título + lista de tasks (worker en línea aparte)
        safe_title = (plan_title or "Sin título de plan").strip()
        if len(safe_title) > 80:
            safe_title = safe_title[:80] + "..."
        try:
            _tlist = list(tasks or [])[:8]
            tasks_preview = ", ".join(_tlist)
            if len(tasks or []) > 8:
                tasks_preview += ", …"
        except Exception:
            tasks_preview = ""
        if len(tasks_preview) > 200:
            tasks_preview = tasks_preview[:200] + "…"
        log_plan(
            _obs,
            '"%s" | tasks: [%s]',
            safe_title or "(vacío)",
            tasks_preview if tasks_preview else "(sin tareas)",
        )
        _assigned_for_log = (out.get("assigned_worker_id") or assigned or "").strip() or "?"
        log_sys(_obs, "Worker elegido para el plan: %s", _assigned_for_log)
        return out

    def invoke_worker_node(state: ManagerAgentState, config: RunnableConfig) -> ManagerAgentState:
        """Invoca el grafo del worker asignado; set_busy/set_idle y append_task_audit. Solo invoca si el worker existe en templates."""
        chat_id = state.get("chat_id") or ""
        from duckclaw.graphs.chat_cancel import ChatCancelledError, raise_if_chat_cancelled

        try:
            raise_if_chat_cancelled(str(chat_id or "").strip())
        except ChatCancelledError:
            set_idle(chat_id)
            return {
                "reply": "Interrumpido.",
                "_audit_done": True,
                "assigned_worker_id": (state.get("assigned_worker_id") or "").strip() or None,
            }
        tenant_id = state.get("tenant_id") or "default"
        user_id = state.get("user_id") or chat_id or "default"
        vault_db_path = (state.get("vault_db_path") or "").strip()
        shared_db_path = (state.get("shared_db_path") or "").strip()
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        planned_task = (state.get("planned_task") or "").strip() or incoming
        plan_title = (state.get("plan_title") or "").strip() or None
        history = state.get("history") or []
        available = list(state.get("available_templates") or list_workers(troot, db=db, tenant_id=tenant_id))
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        _all_iw = list_workers(troot, db=db, tenant_id=tenant_id)
        if assigned and assigned not in available and _is_entry_route_system_event(incoming):
            _entry_iw = (state.get("entry_worker_id") or "").strip()
            _c_iw = _resolve_template_id(_all_iw, assigned) or (
                _resolve_template_id(_all_iw, _entry_iw) if _entry_iw else None
            )
            if _c_iw and _c_iw in _all_iw:
                assigned = _c_iw
                if _c_iw not in available:
                    available = list(available) + [_c_iw]
        if assigned not in available:
            assigned = available[0] if available else None
        if assigned:
            try:
                from duckclaw.vaults import resolve_template_vault_path
                from duckclaw.workers.manifest import load_manifest

                _spec_del = load_manifest(assigned)
                _tpl_vault = resolve_template_vault_path(
                    _spec_del.forge_vault_binding, user_id
                )
                if _tpl_vault:
                    vault_db_path = _tpl_vault
            except Exception:
                pass
        if assigned is None:
            set_idle(chat_id)
            _log.warning("manager: no hay plantillas de worker disponibles en %s", getattr(troot, "__str__", lambda: "")() or "forge/templates")
            # No incluir "messages": None — add_messages en ManagerAgentState exige valores no nulos.
            return {
                "reply": "No hay plantillas de worker configuradas. Añade al menos una en forge/templates (con manifest.yaml).",
                "_audit_done": True,
                "assigned_worker_id": None,
            }
        task_summary = (state.get("task_summary") or "").strip() or _task_summary_for_activity(incoming, planned_task)
        planned_task_for_worker = preserve_context_blocks_for_worker(
            incoming,
            planned_task,
            explicit_storage_request=explicit_duckdb_schema_request,
        )
        _combined = planned_task_for_worker or incoming
        _lite_stdio_mcp = _worker_should_use_lite_stdio_mcp_surface(_combined)
        _url_research_mcp = _worker_should_use_url_research_mcp_surface(_combined)
        _visual_lite_mcp = _manager_visual_generation_intent(_combined)
        _summarize_vault_ro = _incoming_has_context_summary_system_directive(_combined)
        t0 = time.monotonic()
        reply = ""
        messages = None
        worker_invoke: dict[str, Any] | None = None
        status = "SUCCESS"
        agent_instance_label = ""
        slot_token = ""
        run_label_n = 1
        raw_worker_reply = ""
        worker_graph = None
        worker_cache_key = ""
        _suspend_for_rw_worker = False
        _suspend_hub_for_visual_delta = False
        _will_suspend_ro = False
        _vault_lock_obj: threading.Lock | None = None
        pa = int(state.get("plan_attempt_index") or 0)
        max_a = int(state.get("plan_max_attempts") or _initial_replan_state()["plan_max_attempts"])
        reasons_acc = list(state.get("plan_failure_reasons") or [])
        _tools_list: list[str] = []
        replan_after = False
        exhausted_final = False
        next_plan_attempt = pa
        try:
            global _worker_graph_cache
            slot_token, run_label_n = acquire_subagent_slot(tenant_id, assigned, str(chat_id or ""))
            agent_instance_label = f"{assigned} {run_label_n}".strip()
            worker_cache_key = (
                f"{tenant_id}::{assigned}::{vault_db_path or db_path or ''}::{shared_db_path}"
                f"::{(llm_provider or '').strip()}::{(llm_model or '').strip()}::{(llm_base_url or '').strip()}"
            )
            if _visual_lite_mcp:
                worker_cache_key = f"{worker_cache_key}::vis_gen"
            elif _lite_stdio_mcp:
                worker_cache_key = f"{worker_cache_key}::ctx_syn"
            elif _url_research_mcp:
                low_url = (_combined or "").strip().lower()
                _url_tag = "reddit" if "reddit.com" in low_url else ("mql5" if "mql5.com" in low_url else "url")
                worker_cache_key = f"{worker_cache_key}::url_{_url_tag}"
            else:
                # No mezclar grafos con Reddit MCP (cold start npx) y turnos sin Reddit.
                low_full = (_combined or "").strip().lower()
                worker_cache_key = (
                    f"{worker_cache_key}::mcp_rd"
                    if "reddit.com" in low_full
                    else f"{worker_cache_key}::lean_full"
                )
            if _summarize_vault_ro:
                worker_cache_key = f"{worker_cache_key}::sum_vault_ro"
            from duckclaw.workers.factory import _get_db_path, _same_duckdb_file
            from duckclaw.workers.manifest import load_manifest

            spec_inv = load_manifest(assigned, troot, db=db, tenant_id=tenant_id)
            mgr_path = str(getattr(db, "_path", "") or "").strip()
            worker_resolved = _get_db_path(
                assigned, tenant_id, (vault_db_path or db_path or None)
            ).strip()
            _mgr_read_only = bool(getattr(db, "_read_only", False))
            # Misma resolución que build_worker_graph; vault_db_path crudo puede diverger del path real.
            _needs_rw_vault = (not bool(spec_inv.read_only)) and (not bool(_summarize_vault_ro))
            _hub_same_as_worker = bool(
                worker_resolved and mgr_path and _same_duckdb_file(mgr_path, worker_resolved)
            )
            _shared_resolved_inv = ""
            try:
                from duckclaw.workers.factory import _resolve_shared_db_path

                _shared_resolved_inv = (_resolve_shared_db_path(spec_inv, shared_db_path or None) or "").strip()
            except Exception:
                pass
            _will_skip_private = bool(
                not _mgr_read_only
                and _hub_same_as_worker
                and not _shared_resolved_inv
                and not _summarize_vault_ro
            )
            # DuckDB: no RO+RW simultáneo al mismo archivo. Suspender el RO del manager antes
            # de abrir el worker RW; leer sandbox/chat_state antes (sin worker RW abierto).
            _suspend_for_rw_worker = bool(
                _mgr_read_only and _needs_rw_vault and _hub_same_as_worker
            )
            # VISUAL_ASSET_UPSERT escribe en hub (get_gateway_db_path), no en vault del worker.
            # El manager mantiene RO al hub durante ComfyUI (~3–4 min); suspender evita lock con db-writer.
            _suspend_hub_for_visual_delta = bool(
                _mgr_read_only and _visual_lite_mcp and mgr_path
            )
            _will_suspend_ro = _suspend_for_rw_worker or _suspend_hub_for_visual_delta
            _spawn_inline_writes = False
            try:
                from duckclaw.spawn_profile import spawn_inline_writes_enabled

                _spawn_inline_writes = bool(spawn_inline_writes_enabled())
            except Exception:
                pass
            # Serializa acceso al .duckdb: dos webhooks concurrentes no deben abrir dos DuckClaw RW.
            _vk = _vault_lock_key(worker_resolved)
            if _vk:
                with _vault_invoke_guard:
                    if _vk not in _vault_invoke_locks:
                        _vault_invoke_locks[_vk] = threading.Lock()
                    _vault_lock_obj = _vault_invoke_locks[_vk]
                _vault_lock_obj.acquire()
            _cfg_db = _agent_config_db_for_vault(db, vault_db_path or None)
            raw_sb = get_chat_state(_cfg_db, chat_id, "sandbox_enabled")
            sb_on = (raw_sb or "").strip().lower() in ("true", "1", "on", "sí", "si")
            db_display = vault_db_path or db_path or "(unknown)"
            if _will_suspend_ro:
                db.suspend_readonly_file_handle()
            if _visual_lite_mcp:
                try:
                    from duckclaw.forge.skills.visual_state_delta import set_visual_state_delta_hub_db

                    set_visual_state_delta_hub_db(db)
                except Exception:
                    pass
            try:
                from duckclaw.forge.skills.visual_provider import resolve_visual_provider

                _vis_prov = resolve_visual_provider(_cfg_db, chat_id)
            except Exception:
                _vis_prov = "local"
            worker_cache_key = f"{worker_cache_key}::visprov_{_vis_prov}"
            if worker_cache_key not in _worker_graph_cache:
                _worker_graph_cache[worker_cache_key] = _build_worker_graph(
                    assigned,
                    vault_db_path or db_path,
                    llm,
                    templates_root=troot,  # None => forge/templates
                    llm_provider=llm_provider or "",
                    llm_model=llm_model or "",
                    llm_base_url=llm_base_url or "",
                    instance_name=tenant_id,  # Aislar por tenant (Forge/WorkerFactory)
                    shared_db_path=shared_db_path or None,
                    reuse_db=db,
                    db=db,
                    tenant_id=tenant_id,
                    tool_surface=(
                        "visual_generation"
                        if _visual_lite_mcp
                        else (
                            "context_synthesis"
                            if _lite_stdio_mcp
                            else ("url_research" if _url_research_mcp else "full")
                        )
                    ),
                    incoming_hint=_combined,
                    open_vault_read_only=_summarize_vault_ro,
                    chat_id=str(chat_id or ""),
                    config_db=_cfg_db,
                )
            worker_graph = _worker_graph_cache[worker_cache_key]
            set_log_context(
                tenant_id=tenant_id,
                worker_id=assigned,
                chat_id=format_chat_log_identity(chat_id or "unknown", state.get("username")),
            )
            log_sys(_obs, "Delegación: manager -> %s", assigned)
            log_sys(
                _obs,
                "Sandbox: %s | DB: %s",
                "ON" if sb_on else "OFF",
                db_display,
            )
            # Pasar la tarea planificada al worker para que use herramientas y no responda genérico
            # Incluimos chat_id para que el worker pueda leer sandbox_enabled por sesión.
            _out_hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
            _user_incoming_invoke = (state.get("user_incoming") or incoming or "").strip()
            worker_state = {
                "input": planned_task_for_worker,
                "incoming": planned_task_for_worker,
                "user_incoming": _user_incoming_invoke,
                "history": history,
                "chat_id": chat_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "username": (state.get("username") or "").strip(),
                "vault_db_path": vault_db_path,
                "shared_db_path": shared_db_path,
                "subagent_instance_label": agent_instance_label,
                "heartbeat_plan_title": (plan_title or "").strip(),
                "subagent_turn_started_monotonic": time.monotonic(),
            }
            if _out_hb_tok:
                worker_state["outbound_telegram_bot_token"] = _out_hb_tok
            worker_state["plan_attempt_index"] = pa
            worker_state["plan_max_attempts"] = max_a
            mission = state.get("active_mission")
            if (
                isinstance(mission, dict)
                and _worker_matches_id(assigned, mission.get("target_worker"))
            ):
                worker_state["suppress_subagent_egress"] = True
                try:
                    from duckclaw.graphs.chat_heartbeat import schedule_chat_heartbeat_dm

                    target_name = str(mission.get("target_worker") or assigned or "subagente")
                    source_name = str(mission.get("source_worker") or "manager")
                    handoff_msg = (
                        f"A2A handoff visible: @{target_name}, solicitado por @{source_name} "
                        "para misión en curso."
                    )
                    schedule_chat_heartbeat_dm(
                        str(tenant_id or "default").strip() or "default",
                        str(chat_id or "").strip(),
                        str(user_id or "").strip() or str(chat_id or "").strip(),
                        handoff_msg,
                        log_worker_id=agent_instance_label or None,
                        log_username=(state.get("username") or "").strip() or None,
                        log_plan_title="A2A handoff",
                        outbound_bot_token=_out_hb_tok,
                        routing_worker_id=str(assigned or "").strip() or None,
                    )
                except Exception:
                    pass
            if state.get("handoff_context"):
                worker_state["handoff_context"] = state.get("handoff_context")
            mission_context_system_message = (state.get("mission_context_system_message") or "").strip()
            if mission_context_system_message:
                from langchain_core.messages import SystemMessage

                worker_state["messages"] = [SystemMessage(content=mission_context_system_message)]
            trace_cfg = get_tracing_config(
                tenant_id,
                assigned,
                str(chat_id or "unknown"),
                base=config,
            )
            from duckclaw.graphs.chat_heartbeat import (
                format_delegation_heartbeat_message,
                is_admin_ui_chat_session,
                schedule_chat_heartbeat_dm,
            )

            _cid_hb = str(chat_id or "").strip()
            if not is_admin_ui_chat_session(_cid_hb):
                _tasks_for_hb = state.get("tasks")
                _hb_text = format_delegation_heartbeat_message(
                    state.get("plan_title"),
                    _tasks_for_hb if isinstance(_tasks_for_hb, list) else [],
                    task_summary=task_summary,
                    subagent_header=agent_instance_label or None,
                )
                _hb_plan_log = (plan_title or "").strip() or None
                schedule_chat_heartbeat_dm(
                    str(tenant_id or "default").strip() or "default",
                    _cid_hb,
                    str(user_id or "").strip() or _cid_hb,
                    _hb_text,
                    log_worker_id=agent_instance_label or None,
                    log_username=(state.get("username") or "").strip() or None,
                    log_plan_title=_hb_plan_log,
                    outbound_bot_token=_out_hb_tok,
                    routing_worker_id=str(assigned or "").strip() or None,
                )
            try:
                raise_if_chat_cancelled(str(chat_id or "").strip())
                worker_invoke = worker_graph.invoke(worker_state, trace_cfg)
            except ChatCancelledError:
                set_idle(chat_id)
                return {
                    "reply": "Interrumpido.",
                    "_audit_done": True,
                    "assigned_worker_id": str(assigned or "").strip() or None,
                }
            _wdb_peek = getattr(worker_graph, "_worker_db", None)
            if _wdb_peek is not None and _wdb_peek is not db:
                _peek_rw = not bool(getattr(_wdb_peek, "_read_only", False))
                if _suspend_for_rw_worker or _peek_rw:
                    _release_worker_db_handle(worker_graph, cache_key=worker_cache_key)
            raw_worker_reply = str(
                worker_invoke.get("internal_reply")
                or worker_invoke.get("reply")
                or worker_invoke.get("output")
                or "Sin respuesta."
            )
            reply = raw_worker_reply
            _label_reply = f"{assigned} {run_label_n}".strip()
            # CRM (Next.js): el proxy usa chat_id `crm-ticket-*`; no anteponer etiqueta de subagente.
            _crm = str(chat_id or "").strip().lower().startswith("crm-ticket-")
            if _visual_lite_mcp and isinstance(worker_invoke, dict):
                _vis_b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
                _vis_aid = (worker_invoke.get("visual_artifact_id") or "").strip()
                if _vis_b64 or _vis_aid:
                    _short_vis = (raw_worker_reply or "").strip()
                    if not _short_vis or len(_short_vis) > 240:
                        _short_vis = "Imagen generada."
                    reply = _short_vis
            if not _crm:
                reply = _prepend_subagent_label_once(reply, _label_reply)
            messages = worker_invoke.get("messages")
            if isinstance(messages, tuple):
                messages = list(messages)
            # Log tool use para PM2 (tras manager plan)
            _tools_list = _worker_tool_names_from_messages(messages if isinstance(messages, list) else None)
            _log.info(
                "manager tool_use: delegó a worker=%s | tools usadas=%s",
                assigned,
                _tools_list if _tools_list else "ninguna",
            )
            _w_llm_failed = bool(worker_invoke.get("_duckclaw_worker_llm_invoke_failed"))
            _w_llm_transient = bool(worker_invoke.get("_duckclaw_worker_llm_transient"))
            _soft_would_match = worker_reply_suggests_replan_without_tools(raw_worker_reply)
            if replan_enabled() and status == "SUCCESS":
                if _w_llm_failed and _w_llm_transient:
                    _fk = (worker_invoke.get("_duckclaw_worker_llm_failure_kind") or "error").strip()
                    _rworker = f"inferencia: fallo de conexión al backend LLM en el worker ({_fk})"
                    reasons_acc = merge_failure_reasons(reasons_acc, _rworker)
                    if pa + 1 < max_a:
                        replan_after = True
                        next_plan_attempt = pa + 1
                        log_sys(
                            _obs,
                            "manager replan: worker LLM transitorio -> intento %s/%s (%s)",
                            pa + 2,
                            max_a,
                            _rworker,
                        )
                    else:
                        exhausted_final = True
                elif _w_llm_failed and not _w_llm_transient:
                    reasons_acc = merge_failure_reasons(
                        reasons_acc,
                        "inferencia: error no transitorio en invoke del worker "
                        f"({(worker_invoke.get('_duckclaw_worker_llm_failure_kind') or 'unknown')})",
                    )
                else:
                    try:
                        from duckclaw.workers.tool_orchestration import (
                            parse_tool_orchestration,
                            replan_rule_triggered,
                        )

                        _orch_replan = parse_tool_orchestration(spec_inv)
                        if _orch_replan:
                            _orch_trig, _orch_reason = replan_rule_triggered(
                                _orch_replan,
                                _combined,
                                _tools_list,
                            )
                            if _orch_trig:
                                reasons_acc = merge_failure_reasons(reasons_acc, _orch_reason)
                                if pa + 1 < max_a:
                                    replan_after = True
                                    next_plan_attempt = pa + 1
                                    log_sys(
                                        _obs,
                                        "manager replan: tool_orchestration -> intento %s/%s (%s)",
                                        pa + 2,
                                        max_a,
                                        _orch_reason,
                                    )
                                else:
                                    exhausted_final = True
                    except Exception:
                        pass
                    if not replan_after and not _tools_list and _soft_would_match:
                        _rsoft = "inferencia: respuesta sin tools con indicios de fallo de backend"
                        reasons_acc = merge_failure_reasons(reasons_acc, _rsoft)
                        if pa + 1 < max_a:
                            replan_after = True
                            next_plan_attempt = pa + 1
                            log_sys(
                                _obs,
                                "manager replan: señal débil (sin tools) -> intento %s/%s",
                                pa + 2,
                                max_a,
                            )
                        else:
                            exhausted_final = True
        except Exception as e:
            msg = str(e)[:2048]
            low = msg.lower()
            # DuckDB usa "Connection Error" al mezclar RO/RW en el mismo archivo; no confundir con MLX caído.
            _duckdb_config_clash = (
                "same database file" in low and "different configuration" in low
            ) or ("duckdb" in low and "read_only" in low)
            if (
                not _duckdb_config_clash
                and any(
                    x in low
                    for x in (
                        "connection error",
                        "connection refused",
                        "remote protocol",
                        "failed to establish",
                        "errno 61",
                        "econnrefused",
                    )
                )
            ):
                msg = (
                    "El backend de inferencia (p. ej. MLX en :8080) no está disponible o se reinició; "
                    "suele ir ligado a OOM en Metal. Revisa `pm2 logs MLX-Inference` y, si usas resúmenes largos "
                    "de contexto, reduce `DUCKCLAW_SEMANTIC_SUMMARY_MAX_CHARS`.\n\n"
                    f"Detalle: {str(e)[:400]}"
                )
            reply = msg
            _label_e = f"{assigned} {run_label_n}".strip()
            _crm_e = str(chat_id or "").strip().lower().startswith("crm-ticket-")
            if not _crm_e:
                reply = _prepend_subagent_label_once(reply, _label_e)
            status = "FAILED"
            _retryable, _rreason = classify_exception_for_replan(e, _duckdb_config_clash)
            if replan_enabled() and _retryable:
                reasons_acc = merge_failure_reasons(reasons_acc, _rreason)
                if pa + 1 < max_a:
                    replan_after = True
                    next_plan_attempt = pa + 1
                    log_sys(
                        _obs,
                        "manager replan: excepción recuperable -> intento %s/%s (%s)",
                        pa + 2,
                        max_a,
                        _rreason,
                    )
                else:
                    exhausted_final = True
        finally:
            _wdb = getattr(worker_graph, "_worker_db", None) if worker_graph is not None else None
            # DuckDB: un worker RW no debe dejar el .duckdb abierto en caché cuando el manager
            # no pasó por suspend RO (hub vs vault distinto en path); si no, db-writer y task_audit_log pierden lock
            # (evidencia 2026-05-12: IO Error durante append_task_audit).
            _worker_rw = _wdb is not None and not bool(getattr(_wdb, "_read_only", False))
            if _wdb is not None and _wdb is not db and (_suspend_for_rw_worker or _worker_rw):
                try:
                    _wdb.close()
                except Exception:
                    pass
                try:
                    _worker_graph_cache.pop(worker_cache_key, None)
                except Exception:
                    pass
            if _visual_lite_mcp:
                try:
                    from duckclaw.forge.skills.visual_state_delta import clear_visual_state_delta_hub_db

                    clear_visual_state_delta_hub_db()
                except Exception:
                    pass
            if slot_token:
                release_subagent_slot(tenant_id, assigned, slot_token, str(chat_id or ""))
            set_idle(chat_id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            # task_audit vía db-writer: no reabrir RO del manager hasta después del enqueue.
            append_task_audit(db, chat_id, assigned, incoming, status, elapsed_ms, plan_title=plan_title)
            if _will_suspend_ro:
                try:
                    db.resume_readonly_file_handle()
                except Exception:
                    pass
            if _vault_lock_obj is not None:
                try:
                    _vault_lock_obj.release()
                except Exception:
                    pass

        if exhausted_final:
            reply = format_exhausted_plan_failure(reasons_acc)

        # El manager ya registró en task_audit_log; el Gateway no debe duplicar.
        # assigned_worker_id para que el Gateway lo use en respuesta y trazas.
        # Solo añadir messages si el worker devolvió lista: None rompe add_messages en el estado.
        out: ManagerAgentState = {
            "reply": reply,
            "_audit_done": True,
            "assigned_worker_id": assigned,
            "plan_title": plan_title,
        }  # type: ignore[assignment]
        if messages is not None:
            out["messages"] = messages
        b64 = ""
        if isinstance(worker_invoke, dict):
            b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
        if not b64 and messages is not None:
            b64 = extract_latest_sandbox_figure_base64(messages) or ""
        if b64:
            out["sandbox_photo_base64"] = b64
        aid = ""
        if isinstance(worker_invoke, dict):
            aid = (worker_invoke.get("visual_artifact_id") or "").strip()
        if aid:
            out["visual_artifact_id"] = aid
        if "active_mission" in state:
            out["active_mission"] = state.get("active_mission")
        if "handoff_context" in state:
            out["handoff_context"] = state.get("handoff_context")
        out["last_worker_raw_reply"] = raw_worker_reply or reply
        out["plan_max_attempts"] = max_a
        out.update(
            _replan_output_fields(
                replan_after=replan_after,
                exhausted_final=exhausted_final,
                next_plan_attempt=next_plan_attempt,
                max_attempts=max_a,
                failure_reasons=reasons_acc,
            )
        )
        return out

    def mercenary_node(state: ManagerAgentState) -> ManagerAgentState:
        """Ejecución efímera Caged Beast: Docker aislado → result.json → respuesta (sin invoke_worker)."""
        from duckclaw.graphs.activity import set_idle
        from duckclaw.graphs.on_the_fly_commands import append_task_audit
        from duckclaw.graphs.sandbox import run_mercenary_ephemeral

        chat_id = state.get("chat_id") or ""
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        plan_title = (state.get("plan_title") or "").strip() or None
        spec = state.get("mercenary_spec")
        assigned = (state.get("assigned_worker_id") or "").strip() or None

        if not isinstance(spec, dict) or not str(spec.get("directive") or "").strip():
            set_idle(chat_id)
            return {
                "reply": "No se pudo ejecutar el mercenario: especificación inválida.",
                "_audit_done": True,
                "assigned_worker_id": assigned,
            }  # type: ignore[return-value]

        directive = str(spec.get("directive") or "").strip()
        timeout_m = max(1, min(int(spec.get("timeout") or 300), 600))
        task_id = uuid.uuid4().hex[:20]
        t0 = time.monotonic()
        result = run_mercenary_ephemeral(directive, timeout_m, task_id=task_id)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        ok = bool(result.get("ok"))
        status = "SUCCESS" if ok else "FAILED"
        try:
            append_task_audit(
                db,
                chat_id,
                "manager",
                incoming[:2000] if incoming else "(mercenary)",
                status,
                elapsed_ms,
                plan_title=plan_title or "Mercenario (sandbox)",
            )
        except Exception:
            pass
        set_idle(chat_id)

        if ok:
            payload = result.get("result") or {}
            body = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(body) > 7500:
                body = body[:7500] + "\n…"
            reply = "**Mercenario (sandbox)** — ejecución aislada completada.\n\n```json\n" + body + "\n```"
        else:
            code = result.get("error_code") or "MERCENARY_ERROR"
            msg = (result.get("message") or "").strip()
            reply = f"**Mercenario:** error `{code}`\n\n{msg}"

        _log.info(
            "manager mercenary: ok=%s code=%s",
            ok,
            result.get("error_code") if not ok else "ok",
        )

        out: ManagerAgentState = {
            "reply": reply,
            "_audit_done": True,
            "assigned_worker_id": assigned,
            "plan_title": plan_title,
        }  # type: ignore[assignment]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        if "available_templates" in state:
            out["available_templates"] = state["available_templates"]
        _ot_m = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_m:
            out["outbound_telegram_bot_token"] = _ot_m
        return out

    def route_after_plan(state: ManagerAgentState) -> str:
        mspec = state.get("mercenary_spec")
        if isinstance(mspec, dict) and str(mspec.get("directive") or "").strip():
            return "mercenary"
        return "invoke_worker"

    def route_after_invoke_worker(state: ManagerAgentState) -> str:
        current_worker = (state.get("assigned_worker_id") or "").strip()
        if state.get("replan_requested"):
            log_sys(_obs, "manager route: replan -> plan (reintento de planificación)")
            return "plan"
        mission = state.get("active_mission")
        if not isinstance(mission, dict):
            return "end"
        target_worker = (mission.get("target_worker") or "").strip()
        if not target_worker or not current_worker:
            return "end"
        if _worker_matches_id(current_worker, target_worker):
            source_w = (mission.get("source_worker") or "").strip()
            available = state.get("available_templates") or []
            if source_w and not any(_worker_matches_id(wid, source_w) for wid in available):
                return "end"
            return "return_to_source"
        return "end"

    def return_to_source_node(state: ManagerAgentState) -> ManagerAgentState:
        mission = state.get("active_mission")
        if not isinstance(mission, dict):
            return {"active_mission": None}  # type: ignore[return-value]
        source_worker = (mission.get("source_worker") or "").strip()
        if not source_worker:
            return {"active_mission": None}  # type: ignore[return-value]

        source_in_team = None
        available = state.get("available_templates") or []
        for wid in available:
            if _worker_matches_id(wid, source_worker):
                source_in_team = wid
                break
        next_worker = source_in_team or source_worker

        mission_result = (state.get("last_worker_raw_reply") or state.get("reply") or "").strip()
        mission_name = (mission.get("mission") or "mission").strip() or "mission"
        _return_policy_db = _agent_config_db_for_vault(
            db,
            (state.get("vault_db_path") or "").strip() or None,
        )
        _return_prompt_policies = PromptPolicyResolver(_return_policy_db)
        target_worker = (mission.get("target_worker") or "").strip() or "subagente"
        mission_system_message = (
            f"El worker {target_worker} completó la misión {mission_name}. "
            f"Resultado crudo: {mission_result}\n\n"
            "Sintetiza el resultado para el usuario sin inventar datos."
        )
        synthesis_task = _load_manager_task_policy(
            _return_prompt_policies,
            "mission_return_synthesis",
            mission_name=mission_name,
            mission_result=mission_result,
            target_worker=target_worker,
        )
        if not synthesis_task:
            synthesis_task = mission_result or mission_name

        out: ManagerAgentState = {
            "assigned_worker_id": next_worker,
            "planned_task": synthesis_task,
            "incoming": synthesis_task,
            "input": synthesis_task,
            "mission_context_system_message": mission_system_message,
            "active_mission": None,
            "handoff_context": None,
        }  # type: ignore[assignment]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        if "available_templates" in state:
            out["available_templates"] = state["available_templates"]
        if state.get("user_incoming"):
            out["user_incoming"] = state.get("user_incoming")
        if state.get("entry_worker_id"):
            out["entry_worker_id"] = state.get("entry_worker_id")
        if "plan_title" in state:
            out["plan_title"] = state["plan_title"]
        if "tasks" in state:
            out["tasks"] = state["tasks"]
        if "task_summary" in state:
            out["task_summary"] = state["task_summary"]
        _tok_rs = (state.get("outbound_telegram_bot_token") or "").strip()
        if _tok_rs:
            out["outbound_telegram_bot_token"] = _tok_rs
        return out

    def route_after_router(state: ManagerAgentState) -> str:
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        if _manager_greeting_fast_path_ok(incoming):
            return "greeting_shortcut"
        if _manager_capabilities_fast_path_ok(incoming):
            return "greeting_shortcut"
        return "plan"

    graph = StateGraph(ManagerAgentState)
    graph.add_node("router", router_node)
    graph.add_node("greeting_shortcut", greeting_shortcut_node)
    graph.add_node("plan", plan_node)
    graph.add_node("mercenary", mercenary_node)
    graph.add_node("invoke_worker", invoke_worker_node)
    graph.add_node("return_to_source", return_to_source_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"greeting_shortcut": "greeting_shortcut", "plan": "plan"},
    )
    graph.add_edge("greeting_shortcut", END)
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {"mercenary": "mercenary", "invoke_worker": "invoke_worker"},
    )
    graph.add_edge("mercenary", END)
    graph.add_conditional_edges(
        "invoke_worker",
        route_after_invoke_worker,
        {
            "return_to_source": "return_to_source",
            "plan": "plan",
            "end": END,
        },
    )
    graph.add_edge("return_to_source", "invoke_worker")
    return graph.compile()
