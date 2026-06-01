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

from duckclaw.forge.atoms.state import ManagerAgentState
from duckclaw.graphs.sandbox import extract_latest_sandbox_figure_base64
from duckclaw.graphs.subagent_run_id import acquire_subagent_slot, release_subagent_slot
from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_plan, log_sys, set_log_context

from duckclaw.guardrails.loader import format_guardrail, load_guardrail, load_guardrail_task_list
from duckclaw.graphs.agent_resilience import (
    classify_exception_for_replan,
    format_exhausted_plan_failure,
    format_replan_task_suffix,
    merge_failure_reasons,
    plan_max_attempts_from_env,
    replan_enabled,
    worker_reply_suggests_replan_without_tools,
)

_log = logging.getLogger(__name__)
_obs = get_obs_logger()
_worker_graph_cache: dict[str, Any] = {}
_vault_invoke_guard = threading.Lock()
_vault_invoke_locks: dict[str, threading.Lock] = {}


def _vault_lock_key(path: str) -> str:
    p = (path or "").strip()
    if not p or p == ":memory:":
        return ""
    try:
        return str(Path(p).expanduser().resolve())
    except Exception:
        return str(Path(p).expanduser())


def _tool_name_from_embedded_json_content(text: str) -> str | None:
    """Si el modelo emitió tool como JSON en el texto (p. ej. MLX sin tool_calls), extrae el nombre."""
    from duckclaw.integrations.llm_providers import coerce_json_tool_invoke

    raw = (text or "").strip()
    got = coerce_json_tool_invoke(raw)
    if got:
        return got[0]
    # Texto antes del objeto JSON (p. ej. "Voy a consultar:\n{\"name\": ...")
    i = raw.find("{")
    if i > 0:
        got = coerce_json_tool_invoke(raw[i:])
        if got:
            return got[0]
    return None


def _messages_turn_for_tool_audit(messages: list[Any]) -> list[Any]:
    """
    Mensajes del turno actual respecto al último HumanMessage (tarea del usuario en el worker).
    Evita mezclar tool_calls de turnos viejos del historial y alinea con prepare_node (último Human = tarea).
    """
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        HumanMessage = ()  # type: ignore[assignment, misc]
    last_u = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict):
            r = str(m.get("role") or m.get("type") or "").lower()
            if r in ("human", "user"):
                last_u = i
                break
        elif HumanMessage and isinstance(m, HumanMessage):
            last_u = i
            break
    if last_u < 0:
        return messages
    return messages[last_u + 1 :]


def _is_ai_like_message(m: Any) -> bool:
    """True si el mensaje es un turno assistant (LangChain o dict ChatML)."""
    if m is None:
        return False
    if isinstance(m, dict):
        r = str(m.get("role") or m.get("type") or "").lower()
        return r in ("ai", "assistant", "model")
    t = getattr(m, "type", None)
    if isinstance(t, str) and t.lower() in ("ai", "assistant"):
        return True
    try:
        from langchain_core.messages import AIMessage

        return isinstance(m, AIMessage)
    except ImportError:
        return False


def _message_body_text_for_embedded_tool(m: Any) -> str:
    """Texto de ``content`` para parsear JSON de tool embebido (dict o BaseMessage)."""
    if isinstance(m, dict):
        from duckclaw.graphs.conversation_traces import _stringify_lc_message_content

        return _stringify_lc_message_content(m.get("content"))
    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    return lc_message_content_to_text(m)


def _worker_tool_names_from_messages(messages: list[Any] | None) -> list[str]:
    """
    Nombres de herramientas usadas en el turno del worker (AIMessage.tool_calls + ToolMessage.name).
    LangChain puede devolver tool_calls como dict o como objetos (p. ej. ToolCall); antes solo se leían dicts
    y los logs del manager mostraban «ninguna» aunque hubiera read_sql/tavily.
    Además: MLX a veces deja la invocación solo en ``content`` JSON sin ``tool_calls``; si no hubo tool_calls/tool
    en el barrido hacia adelante, se busca hacia atrás el último ToolMessage o AIMessage con JSON embebido
    (p. ej. LangGraph devuelve ``messages`` como tupla o el último turno no es assistant).
    """
    if not messages:
        return []
    turn = _messages_turn_for_tool_audit(messages)
    if not turn:
        return []
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        ToolMessage = ()  # type: ignore[assignment, misc]

    names: list[str] = []
    for m in turn:
        if isinstance(m, dict):
            for tc in m.get("tool_calls") or []:
                if isinstance(tc, dict):
                    fn = (tc.get("function") or {}) if isinstance(tc.get("function"), dict) else {}
                    nm = fn.get("name") or tc.get("name")
                else:
                    nm = getattr(tc, "name", None)
                if nm:
                    names.append(str(nm))
            rdict = str(m.get("role") or m.get("type") or "").lower()
            if rdict == "tool":
                tn = m.get("name")
                if tn:
                    names.append(str(tn))
            continue
        for tc in getattr(m, "tool_calls", None) or []:
            nm = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if nm:
                names.append(str(nm))
        addl = getattr(m, "additional_kwargs", None) or {}
        if isinstance(addl, dict):
            for tc in addl.get("tool_calls") or []:
                if isinstance(tc, dict):
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    nm = fn.get("name") if isinstance(fn, dict) else tc.get("name")
                else:
                    nm = getattr(tc, "name", None)
                if nm:
                    names.append(str(nm))
        if ToolMessage and isinstance(m, ToolMessage):
            tn = getattr(m, "name", None)
            if tn:
                names.append(str(tn))
    names = list(dict.fromkeys(names))
    if not names and turn:
        for m in reversed(turn):
            if isinstance(m, dict):
                rdict = str(m.get("role") or m.get("type") or "").lower()
                if rdict == "tool" and m.get("name"):
                    names.append(str(m["name"]))
                    break
                if _is_ai_like_message(m):
                    embedded = _tool_name_from_embedded_json_content(
                        _message_body_text_for_embedded_tool(m).strip()
                    )
                    if embedded:
                        names.append(embedded)
                        break
                continue
            if ToolMessage and isinstance(m, ToolMessage):
                tn = getattr(m, "name", None)
                if tn:
                    names.append(str(tn))
                    break
                continue
            if _is_ai_like_message(m):
                embedded = _tool_name_from_embedded_json_content(
                    _message_body_text_for_embedded_tool(m).strip()
                )
                if embedded:
                    names.append(embedded)
                    break
    names = list(dict.fromkeys(names))
    if not names and turn:
        for m in turn:
            if not _is_ai_like_message(m):
                continue
            blob = _message_body_text_for_embedded_tool(m)
            if re.search(r'["\']name["\']\s*:\s*["\']read_sql["\']', blob) and re.search(
                r'["\']query["\']\s*:', blob, re.IGNORECASE
            ):
                names.append("read_sql")
                break
    return list(dict.fromkeys(names))


def worker_graph_cache_entry_count() -> int:
    """Cuántos grafos de worker hay en caché (tests / diagnóstico / comandos fly)."""
    return len(_worker_graph_cache)


def _release_worker_db_handle(worker_graph: Any | None, *, cache_key: str = "") -> bool:
    """
    Cierra ``_worker_db`` del grafo cacheado y opcionalmente lo saca de la caché.

    Debe llamarse en cuanto termina ``worker_graph.invoke`` si el worker abrió RW en el
    mismo .duckdb que el manager (finanz + admin_sql): dejar el handle abierto hasta el
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
    cuando existe; si no, desde el hub ``hub_db``. Evita mezclar equipo Finanz/Job-Hunter del
    hub multiplex con bots SIATA u otros que comparten chat_id pero usan otro .duckdb.

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


def _worker_id_alnum_slug(worker_id: str | None) -> str:
    """Normaliza id de plantilla (guiones Unicode, espacios) para ramas por worker."""
    return re.sub(r"[^a-z0-9]", "", (worker_id or "").lower())


def _is_job_hunter_worker(worker_id: str | None) -> bool:
    """True si el id de plantilla corresponde a OSINT JobHunter (carpeta Job-Hunter o id job_hunter)."""
    w = (worker_id or "").strip()
    if not w:
        return False
    if _worker_id_alnum_slug(w) == "jobhunter":
        return True
    norm = w.lower()
    for ch in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\uff0d"):
        norm = norm.replace(ch, "-")
    norm = norm.replace("_", "-").strip("-")
    return norm == "job-hunter"


def _incoming_has_context_summary_system_directive(incoming: str) -> bool:
    """Directivas del gateway (/context) con volcado largo (URLs, «oferta», noticias): no son misión Job-Hunter."""
    s = incoming or ""
    return (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in s
        or "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in s
    )


def _incoming_looks_like_semantic_context_followup(incoming: str) -> bool:
    """
    Heurística: el usuario pregunta por notas ya indexadas (VSS) sin pegar el cuerpo.
    Misma superficie de tools que SUMMARIZE_* (stdio MCP liviano / sin Reddit-GitHub-…).
    """
    raw = (incoming or "").strip()
    if not raw or _incoming_has_context_summary_system_directive(raw):
        return False
    t = raw.lower()
    if re.search(
        r"\b(qué|que|hay|algo)\s+.+\s+(en el contexto|en mi contexto|en la memoria)\b",
        t,
    ):
        return True
    if re.search(r"\b(en el contexto|en mi contexto|en la memoria)\s*\?", t):
        return True
    if re.search(
        r"\b(tenemos anotado|hay anotado|notas sobre|contexto indexado|memoria semántica|memoria semantica)\b",
        t,
    ):
        return True
    if "search_semantic" in t:
        return True
    return False


def _worker_should_use_lite_stdio_mcp_surface(text: str) -> bool:
    return _incoming_has_context_summary_system_directive(text) or _incoming_looks_like_semantic_context_followup(
        text
    )


def _worker_should_use_url_research_mcp_surface(text: str) -> bool:
    """
    Mensaje solo URL (HTTPS): omite GitHub/Trends/Reddit en cold start del grafo worker.
    Reddit MCP solo si la URL es reddit.com (``incoming_hint`` en build_worker_graph).
    """
    inc = (text or "").strip()
    if not _LONE_HTTP_URL_ONLY_LINE.match(inc):
        return False
    return not _manager_visual_generation_intent(inc)


def _looks_like_job_add_command(incoming: str) -> bool:
    raw = (incoming or "").strip().lower()
    if not raw:
        return False
    return (raw.startswith("/job --add ") or raw.startswith("/job add ")) and (
        "http://" in raw or "https://" in raw
    )


def job_hunter_user_requests_job_search(incoming: str) -> bool:
    """
    True si el texto del usuario (o la TAREA inyectada) implica búsqueda de empleo con acción concreta.
    Usado por el planner del manager y por el worker (forzar tavily_search en el primer turno).
    """
    raw = (incoming or "").strip()
    if not raw:
        return False
    if _incoming_has_context_summary_system_directive(raw):
        return False
    t = raw.lower()
    is_job_add_command = _looks_like_job_add_command(raw)
    if is_job_add_command:
        return False
    if _job_hunter_user_requests_application_tracking(raw):
        return False
    # Tareas internas de síntesis / retorno A2A: no forzar Tavily.
    if any(
        x in t
        for x in (
            "jobhunter completó",
            "jobhunter completo",
            "completó la misión",
            "completo la mision",
            "sintetiza los resultados",
            "persistió datos en finance_worker",
            "persistio datos en finance_worker",
            "misión a2a job_opportunity_tracking",
            "mision a2a job_opportunity_tracking",
        )
    ):
        return False
    if "tavily_search" in t:
        return True
    if "tarea:" in t and "tavily" in t:
        return True
    # Inyecciones del manager tipo «TAREA: … búsqueda de empleo …» deben disparar Fase 1.
    if t.startswith("tarea:") and any(
        k in t
        for k in (
            "empleo",
            "trabajo",
            "vacante",
            "búsqueda",
            "busqueda",
            "enlace",
            "enlaces",
            "url",
            "postular",
            "linkedin",
            "tavily",
        )
    ):
        return True
    job_terms = (
        "trabajo",
        "empleo",
        "vacante",
        "oferta",
        "linkedin",
        "greenhouse",
        "lever",
        "data scientist",
        "científico de datos",
        "ciencia de datos",
    )
    action_terms = (
        "busca",
        "buscar",
        "encuentra",
        "dame",
        "pásame",
        "pasame",
        "mandame",
        "envía",
        "envia",
        "url",
        "enlace",
        "link",
        "revisar",
        "postular",
        "aplicar",
        "vacantes",
    )
    result = any(x in t for x in job_terms) and (
        any(x in t for x in action_terms) or "http" in t or "www." in t
    )
    return result


def _user_signals_cashflow_stress(incoming: str) -> bool:
    """Detecta estrés de caja / iliquidez en español coloquial."""
    if _incoming_has_context_summary_system_directive(incoming or ""):
        return False
    t = (incoming or "").strip().lower()
    if not t:
        return False
    stress_terms = (
        "iliquido",
        "ilíquido",
        "sin plata",
        "sin dinero",
        "sin liquidez",
        "no me alcanza",
        "no me va a alcanzar",
        "flujo de caja",
        # No incluir «deuda(s)» suelta: consultas de ledger en DuckDB (finanz) suelen decir
        # «resumen de mis deudas» y no deben disparar INCOME_INJECTION / A2A Job-Hunter.
        "necesito ingresos",
        "ingreso extra",
        "ingresos extra",
        "conseguir trabajo",
        "buscar trabajo",
        "buscar empleo",
        "conseguir empleo",
    )
    return any(term in t for term in stress_terms)


def _pick_job_hunter_worker(available_templates: list[str]) -> Optional[str]:
    """Retorna el worker JobHunter presente en el team efectivo."""
    for wid in available_templates or []:
        if _is_job_hunter_worker(wid):
            return wid
    return None


def _finanz_worker_in_templates(available_templates: list[str]) -> bool:
    """True si el equipo incluye al worker finanz (A2A Manager → Finanz → JobHunter → Finanz)."""
    for wid in available_templates or []:
        if _worker_matches_id(wid, "finanz"):
            return True
    return False


def _job_hunter_user_requests_application_tracking(incoming: str) -> bool:
    """
    Seguimiento de postulaciones ya guardadas (DuckDB), sin discovery Tavily.
    Ej.: «dame el seguimiento de las vacantes a las que he aplicado».
    """
    raw = (incoming or "").strip()
    if not raw:
        return False
    tl = raw.lower()
    if tl.startswith("tarea:"):
        return False
    tracking_kw = (
        "seguimiento",
        "postulaciones",
        "postulación",
        "postulacion",
        "aplicaciones enviadas",
        "apliqué",
        "aplique",
        "he aplicado",
        "a las que he aplicado",
        "donde apliqué",
        "donde aplique",
        "estado de mis postul",
        "mis postul",
        "mis aplicaciones",
    )
    if not any(k in tl for k in tracking_kw):
        return False
    job_kw = ("vacante", "vacantes", "empleo", "trabajo", "postul", "aplic", "oferta", "ofertas")
    return any(k in tl for k in job_kw)


def _worker_matches_id(worker_id: str | None, alias: str | None) -> bool:
    """Compara ids de worker tolerando guiones/underscores/case."""
    return _worker_id_alnum_slug(worker_id) == _worker_id_alnum_slug(alias)


def _strip_mercenary_spec_for_browser_worker(
    out: dict[str, Any], templates_root: Path | None = None
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

        spec = load_manifest(wid, templates_root)
        if not getattr(spec, "browser_sandbox", False):
            return False
    except Exception:
        return False
    out.pop("mercenary_spec", None)
    return True


def _strip_mercenary_spec_for_pqrsd_assistant(out: dict[str, Any]) -> bool:
    """Compat tests: mismo criterio que workers con browser_sandbox en manifest."""
    return _strip_mercenary_spec_for_browser_worker(out, None)


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


_LONE_HTTP_URL_ONLY_LINE = re.compile(
    r"^\s*https?://[^\s]+\s*$",
    re.I,
)


def _should_disable_mercenary_for_quant_lone_https_url(
    incoming: str, assigned_worker_id: str | None
) -> bool:
    """
    Mensaje sólo URL (HTTPS/HTTP): el mercenario actual escribe sólo stub (sin scraping real);
    Quant-Trader debe usar tools de lectura web (p. ej. tavily) vía grafo worker.
    """
    if not _worker_matches_id(assigned_worker_id or "", "quant_trader"):
        return False
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((incoming or "").strip()))


def _should_disable_mercenary_for_quant_signal_intent(
    incoming: str, assigned_worker_id: str | None
) -> bool:
    """Quant-Trader: señales/ejecución deben pasar por worker tools, nunca por mercenario stub."""
    if not _worker_matches_id(assigned_worker_id or "", "quant_trader"):
        return False
    low = (incoming or "").strip().lower()
    if not low:
        return False
    if "/execute-signal" in low or "/execute_signal" in low:
        return True
    signal_markers = (
        "señal",
        "senal",
        "signal_id",
        "propose_trade_signal",
        "execute_approved_signal",
        "rebalance",
        "ticker",
        "tickers",
        "ibkr",
    )
    return any(k in low for k in signal_markers)


_QUANT_WEB_RESEARCH_MERCENARY_STRIP_RE = re.compile(
    r"\b(?:investiga(?:r)?|buscar|búsqueda|noticias|acuerdos?|tratos?|"
    r"hallazgos|comunicados?|"
    r"search\s+for|web\s+search|news\s+(?:about|recent)|tavily)\b",
    re.I,
)


def _should_disable_mercenary_for_quant_external_research(
    incoming: str,
    assigned_worker_id: str | None,
    tasks: list[str] | None,
    plan_title: str | None,
) -> bool:
    """
    Quant-Trader: planes tipo «investigar / buscar noticias» deben usar tavily/reddit en el worker;
    el mercenario actual sólo devuelve stub_completed.
    """
    if not _worker_matches_id(assigned_worker_id or "", "quant_trader"):
        return False
    blob = " ".join(
        [
            incoming or "",
            plan_title or "",
            " ".join(str(t) for t in (tasks or []) if t),
        ]
    )
    if not blob.strip():
        return False
    return bool(_QUANT_WEB_RESEARCH_MERCENARY_STRIP_RE.search(blob))


def _contains_income_injection_request(text: str) -> bool:
    """Detecta marcador explícito de handoff A2A desde la respuesta de Finanz."""
    t = (text or "").strip().lower()
    return "[a2a_request: income_injection]" in t


def _contains_job_opportunity_tracking_request(text: str) -> bool:
    """Handoff A2A: Finanz pide que JobHunter persista vacante/postulación en job_opportunities."""
    t = (text or "").strip().lower()
    return "[a2a_request: job_opportunity_tracking]" in t


def route_finanz_reply_a2a_branch(state: dict) -> str | None:
    """
    ``handoff_job_track`` / ``handoff_to_target`` solo si Finanz está en el equipo efectivo.
    Una sola fuente de verdad para el router tras ``invoke_worker`` (y tests).
    """
    if not _finanz_worker_in_templates(list(state.get("available_templates") or [])):
        return None
    current_worker = (state.get("assigned_worker_id") or "").strip()
    raw_reply = state.get("last_worker_raw_reply") or state.get("reply") or ""
    if _worker_matches_id(current_worker, "finanz") and _contains_job_opportunity_tracking_request(raw_reply):
        return "handoff_job_track"
    if _worker_matches_id(current_worker, "finanz") and _contains_income_injection_request(raw_reply):
        return "handoff_to_target"
    return None


# Líneas tipo «finanz 2», «Job-Hunter 1» al inicio del cuerpo (eco de heartbeats / historial).
# El número es subagent_slot_rank (Redis), no réplica PM2 — ver subagent_run_id.
_SUBAGENT_INSTANCE_HEADER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s+\d+\s*$")


def _strip_leading_subagent_instance_headers(text: str) -> str:
    """
    Elimina una o más líneas iniciales ``<worker_id> <n>`` que el modelo repite tras ver
    DMs de delegación o turnos anteriores. Deja intacto el resto del mensaje.
    """
    t = (text or "").strip()
    while t:
        lines = t.splitlines()
        if not lines:
            break
        if not _SUBAGENT_INSTANCE_HEADER_LINE.match(lines[0].strip()):
            break
        t = "\n".join(lines[1:]).strip()
    return t


_CAVEMAN_WORKER_HEADER_RE = re.compile(
    r"(?:^\s*\*\*(?P<b>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\d+[^*]*\*\*"
    r"|^\s*(?P<p>[A-Za-z0-9][A-Za-z0-9_.-]*)\s+\d+(?:\s+·|\s*$))",
    re.MULTILINE | re.IGNORECASE,
)


def _worker_base_from_subagent_label(label: str) -> str:
    """``Quant-Trader 4`` → ``Quant-Trader``; ``finanz`` sin slot queda igual."""
    clean = (label or "").strip()
    if not clean:
        return ""
    parts = clean.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0].strip()
    return clean


def _reply_already_has_worker_header(reply: str, worker_base: str) -> bool:
    """
    True si el worker ya firmó la respuesta (Caveman ``**Worker N · … COT**``,
    línea plana ``Worker N``, o etiqueta de subagente al inicio).
    """
    base = (worker_base or "").strip()
    if not base:
        return False
    text = (reply or "").strip()
    if not text:
        return False
    esc = re.escape(base)
    if re.search(rf"(?m)^\s*\*\*{esc}\s+\d+[^*]*\*\*", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*\*\*{esc}[^*]*\bCOT\b[^*]*\*\*", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*{esc}\s+\d+\b", text, re.IGNORECASE):
        return True
    if re.search(rf"(?m)^\s*{esc}\s*·[^\n]*\bCOT\b", text, re.IGNORECASE):
        return True
    for m in _CAVEMAN_WORKER_HEADER_RE.finditer(text):
        found = (m.group("b") or m.group("p") or "").strip()
        if found.lower() == base.lower():
            return True
    return False


def _prepend_subagent_label_once(reply: str, label: str) -> str:
    """
    Añade el encabezado del subagente solo si el texto aún no lo trae al inicio.
    Evita respuestas con doble prefijo como:
    `finanz 1` + `finanz 1` o Caveman + etiqueta manager.
    """
    clean_reply = _strip_leading_subagent_instance_headers(reply or "")
    clean_label = (label or "").strip()
    if not clean_label or not clean_reply:
        return clean_reply
    worker_base = _worker_base_from_subagent_label(clean_label)
    if _reply_already_has_worker_header(clean_reply, worker_base):
        return clean_reply
    # Tolerar un prefijo markdown básico (`**label**`) además del plano.
    if clean_reply.startswith(clean_label):
        return clean_reply
    if clean_reply.startswith(f"**{clean_label}**"):
        return clean_reply
    return f"{clean_label}\n\n{clean_reply}"


def _is_goals_proactive_system_event(text: str) -> bool:
    """True si el mensaje es el SYSTEM_EVENT del ticker de /crons --delta (legado /goals; misma ruta HTTP)."""
    t = (text or "").strip()
    return t.startswith("[SYSTEM_EVENT:") and proactive_review_event_phrase_in_text(t)


def _is_entry_route_system_event(text: str) -> bool:
    """
    True si el inbound debe ejecutarse en ``entry_worker_id`` (worker de la ruta HTTP),
    sin que el manager lo reasigne (p. ej. ticker TRADING_TICK → Quant-Trader vía /quanttrader).
    """
    t = (text or "").strip()
    if _is_goals_proactive_system_event(t):
        return True
    if not t.startswith("[SYSTEM_EVENT:"):
        return False
    return '"type":"TRADING_TICK"' in t or '"type": "TRADING_TICK"' in t


# --- Quant-Trader: "Procede" / sí corto tras pregunta HRP → evitar plan LLM "Inicio de sesión" ---

_QUANT_HRP_AFFIRM_RE = re.compile(
    r"^\s*("
    r"sí|si|ok|dale|adelante|procede|proceda|proceder|"
    r"confirmo|yes|vamos|listo|claro"
    r")\s*\.?[\s!¡?¿]*$",
    re.IGNORECASE | re.UNICODE,
)


def _stringify_turn_content_for_hrp(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and (str(p.get("type") or "").lower() == "text"):
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(x for x in parts if x)
    return str(content)


def _iter_assistant_bodies_newest_first(history: Any) -> list[str]:
    """
    Cuerpos de mensajes assistant (texto) de más reciente a más antiguo.
    Omite turnos vacíos o solo tool (en historial plano de gateway no suelen existir).
    """
    out: list[str] = []
    if not history:
        return out
    for turn in reversed(list(history)):
        if not isinstance(turn, dict):
            continue
        r = str(turn.get("role") or turn.get("type") or "").lower()
        if r not in ("assistant", "ai", "model"):
            continue
        body = _stringify_turn_content_for_hrp(turn.get("content")).strip()
        if body:
            out.append(body)
    return out


def _find_hrp_rebalance_affirm_context_assistant_body(history: Any) -> str | None:
    """
    Localiza el asistente más reciente cuyo texto pide cierre/continuación de un hilo
    HRP (no solo el último mensaje del asistente: p. ej. TSLA vino después del HRP).
    """
    for body in _iter_assistant_bodies_newest_first(history):
        if _assistant_asks_hrp_rebalance_followup(body):
            return body
    return None


def _manager_extract_tickers(text: str) -> list[str]:
    """Extrae tickers US de texto assistant/planned (evita import circular con factory)."""
    raw = str(text or "")
    if not raw:
        return []
    banned = {
        "SYSTEM",
        "EVENT",
        "GOALS",
        "HITL",
        "IBKR",
        "UUID",
        "JSON",
        "SQL",
        "HRP",
        "CFD",
        "PNL",
        "LIVE",
        "PAPER",
        "PARA",
        "LUEGO",
        "CON",
        "DEL",
        "LAS",
        "LOS",
        "QUE",
        "UNA",
        "UNO",
        "POR",
        "AND",
        "THE",
        "FOR",
        "TO",
        "Y",
        "O",
        "TAREA",
        "TASK",
    }
    out: list[str] = []
    seen: set[str] = set()
    for tk in re.findall(r"\b[A-Z]{1,5}\b", raw):
        tk = tk.upper()
        if tk in banned:
            continue
        if tk not in seen:
            out.append(tk)
            seen.add(tk)
    return out


def _manager_hrp_ticker_label(hrp_body: str) -> str:
    tickers = _manager_extract_tickers(hrp_body)
    if len(tickers) >= 2:
        return f"({tickers[0]}/{tickers[1]})"
    if len(tickers) == 1:
        return f"({tickers[0]})"
    return "(HRP)"


def _assistant_asks_generic_confirmation(assistant_text: str) -> bool:
    """Asistente pide confirmación genérica (¿procedo?, ¿deseas?, ¿quieres?, etc.)."""
    t = (assistant_text or "").strip()
    if not t:
        return False
    if "?" not in t and "¿" not in t:
        return False
    low = t.lower()
    # Solo verbos de cierre típicos en español; omitir «autoriz*» (p. ej. TSLA/QQQ) para no bloquear scan HRP.
    return any(
        k in low
        for k in (
            "procedo",
            "proceda",
            "proceder",
            "deseas",
            "quieres",
        )
    )


def _assistant_asks_hrp_rebalance_followup(assistant_text: str) -> bool:
    t = (assistant_text or "").strip()
    if not t:
        return False
    low = t.lower()
    # Frase típica en español pidiendo señales de compra (no "¿procedo?")
    if "deseas" in low and "genere" in low and any(
        x in low for x in ("señal", "señales", "compra", "rebalance", "hrp", "meta", "spy")
    ):
        return True
    if "rebalance_hrp" in low or "rebalanceo hrp" in low or ("rebalanceo" in low and "hrp" in low):
        if "?" in t or "¿" in t or "procedo" in low or "señal" in low or "rebalance" in low:
            return True
    if ("procedo" in low or "proceda" in low) and any(
        x in low
        for x in (
            "señal",
            "rebalance",
            "hrp",
            "meta",
            "spy",
            "alineación",
            "alineacion",
            "ibkr",
        )
    ):
        return True
    if "revisión" in low and "alineación" in low and "hrp" in low and "ibkr" in low:
        return True
    if "pypfopt" in low or "pyportfolioopt" in low or "hierarchical risk" in low or (
        "hrp" in low and any(x in low for x in ("óptim", "optim", "peso", "pypfopt"))
    ):
        if "?" in t or "procedo" in low or "señal" in low or "rebalance" in low or "deseas" in low:
            return True
    return False


def _quant_operational_intent_requires_fly_command(incoming: str) -> bool:
    """Intención operativa clara de señal/ejecución que debe forzar UX de `/quant_cycle`."""
    t = (incoming or "").strip().lower()
    if not t:
        return False
    # Backtests / simulación histórica (sandbox, ML4T, etc.) no son instrucciones de fly `quant_cycle`.
    if any(
        k in t
        for k in (
            "backtest",
            "backtesting",
            "walk-forward",
            "walk forward",
            "retrotest",
        )
    ):
        return False
    if t.startswith("/quant_cycle"):
        return False
    if re.search(
        r"\b(genera|genera(r)?|crea|crear|ejecuta|ejecutar|lanza|activar|activa|procede|proceder)\b",
        t,
    ) and re.search(r"\b(señal|senal|trade|entrada|compra|rebalance|hrp)\b", t):
        return True
    if "señal real" in t or "senal real" in t:
        return True
    if "genera una señal" in t or "genera una senal" in t:
        return True
    if "ejecút" in t or "ejecut" in t:
        return True
    return False


def _try_quant_hrp_affirm_followup(
    incoming: str,
    history: Any,
    assigned: str,
    tenant_id: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    if not _QUANT_HRP_AFFIRM_RE.match((incoming or "").strip()):
        return None
    plans = [str(x) for x in (available_plan or []) if x]
    if "Quant-Trader" not in plans:
        return None
    w = (assigned or "").strip()
    _tid = (tenant_id or "").strip().lower()
    if w != "Quant-Trader" and _tid != "cuantitativo":
        return None
    _bodies = _iter_assistant_bodies_newest_first(history)
    newest = _bodies[0] if _bodies else None
    if newest and _assistant_asks_hrp_rebalance_followup(newest):
        last_a = newest
    elif newest and _assistant_asks_generic_confirmation(newest):
        return None
    else:
        last_a = _find_hrp_rebalance_affirm_context_assistant_body(history)
    if not last_a:
        return None
    _ticker_label = _manager_hrp_ticker_label(last_a)
    title = f"Confirmación rebalanceo HRP {_ticker_label}"
    task_list = [
        load_guardrail("manager_tasks", "quant_hrp_affirm_task_confirm"),
        load_guardrail("manager_tasks", "quant_hrp_affirm_task_flow"),
    ]
    # Prefijo con símbolos evita que `_quant_extract_tickers` tome "TAREA" o ejemplos (TSLA, …) como ticker primario.
    planned = f"{_ticker_label} " + load_guardrail("manager_tasks", "quant_hrp_affirm_planned")
    return (title, task_list, planned, "Quant-Trader")


def _manager_visual_generation_intent(incoming: str) -> bool:
    """Pedido explícito de imagen (txt2img) → delegar a Quant-Trader sin planner MLX."""
    s = (incoming or "").strip()
    if not s or len(s) > 2000:
        return False
    low = s.lower()
    if re.search(
        r"(?:\b(?:genera|generar|crea|crear|dibuja|dibujar|haz(?:me)?|hacer|pinta|pintar)\b.{0,50}\b(?:imagen(?:es)?|foto(?:s)?|ilustraci[oó]n(?:es)?|caricatura(?:s)?|avatar(?:es)?|picture|image(?:s)?)\b)",
        low,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:txt2img|text-to-image|stable\s*diffusion|comfyui)\b",
            low,
            re.IGNORECASE,
        )
    )


def _pick_quant_trader_worker(available_templates: list[str]) -> Optional[str]:
    for wid in available_templates or []:
        if _worker_matches_id(wid, "quant_trader"):
            return wid
    return None


def _try_visual_generation_fast_plan(
    incoming: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    """Evita planner MLX lento en admin/Telegram cuando el usuario pide una imagen."""
    if not _manager_visual_generation_intent(incoming):
        return None
    qt = _pick_quant_trader_worker(available_plan)
    if not qt:
        return None
    title = "Generar imagen (ComfyUI)"
    task_list = [
        "Usar generate_visual_asset una sola vez con el prompt del usuario.",
        "No repetir la herramienta si ya hubo un ToolMessage OK en este turno.",
    ]
    planned = (incoming or "").strip()
    log_sys(_obs, "Plan rápido imagen → %s (sin planner MLX)", qt)
    return (title, task_list, planned, qt)


def _try_quant_url_research_fast_plan(
    incoming: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    """
    Mensaje solo URL (HTTPS): evita planner MLX lento (admin con historial largo de imágenes).
    Telegram suele ser más rápido porque el chat_id tiene pocos turnos; el admin reutiliza el mismo
    chat_id con decenas de turnos ComfyUI en Redis.
    """
    inc = (incoming or "").strip()
    if not _LONE_HTTP_URL_ONLY_LINE.match(inc):
        return None
    if _manager_visual_generation_intent(inc):
        return None
    qt = _pick_quant_trader_worker(available_plan)
    if not qt:
        return None
    low = inc.lower()
    if "reddit.com" in low:
        title = "Investigar enlace Reddit"
        task_list = [
            "Usar reddit_get_post o reddit_search_reddit con el enlace del usuario.",
            "Sintetizar hallazgos; no inventar contenido del post.",
        ]
    elif "mql5.com" in low:
        title = "Extraer código MQL5 (browser)"
        task_list = [
            "Usar run_browser_sandbox primero (PROTOCOLO MQL5, plantilla stealth).",
            "No usar solo tavily_search sin haber pasado por el sandbox para esta URL.",
        ]
    else:
        title = "Investigar URL"
        task_list = [
            "Usar run_browser_sandbox o tavily_search según el dominio.",
            "Entregar resumen con evidencia de tools del mismo turno.",
        ]
    planned = inc
    log_sys(_obs, "Plan rápido URL → %s (sin planner MLX)", qt)
    return (title, task_list, planned, qt)


_FINANZ_TOOL_PRESSURE_TASK = load_guardrail("manager_tasks", "finanz_tool_pressure")


def _finanz_user_demands_tool_evidence_from_db(text_lower: str) -> bool:
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


def _sanitize_finanz_manager_plan_title(
    plan_title: str | None,
    incoming: str,
    assigned_worker_id: str | None,
) -> str:
    """Evita plan_title tipo «sin herramientas» cuando el usuario exige DuckDB/tools (Planner LLM a veces alucina)."""
    if (assigned_worker_id or "").strip().lower() != "finanz":
        return (plan_title or "").strip()
    title = (plan_title or "").strip()
    if not title:
        return title
    user_tool_pressure = _finanz_user_demands_tool_evidence_from_db((incoming or "").lower())
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


def _plan_task(incoming: str, worker_id: str) -> tuple[str, Optional[str]]:
    """
    Convierte el mensaje del usuario en una tarea explícita para el subagente.
    Retorna (planned_task, override_worker_id).
    override_worker_id: si la intención es DB/tablas y el rol actual es personalizable, delegar a finanz si existe.
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
    t = text.lower()
    override: Optional[str] = None
    _explicit_duckdb_schema_request = bool(
        re.search(
            r"\b(listar\s+tablas|tablas\s+disponibles|qu[ée]\s+tablas|que\s+tablas|"
            r"tablas\s+de\s+la\s+base|tablas\s+en\s+(la\s+)?(base|duckdb)|"
            r"show\s+tables|information_schema\.tables|"
            r"esquema\s+de\s+la\s+base|schema\s+de\s+la\s+base|estructura\s+de\s+la\s+base|"
            r"listar\s+(el\s+)?esquema|ver\s+(el\s+)?esquema|mostrar\s+(el\s+)?esquema|"
            r"nombre\s+de\s+la\s+db|nombre\s+db)\b",
            t,
        )
        or (
            re.search(r"\b(tables|tablas)\b", t)
            and re.search(r"\b(base|duckdb|datos|database|bd)\b", t)
        )
    )
    if (worker_id or "").strip().lower() == "quant-trader" and _quant_operational_intent_requires_fly_command(text):
        return load_guardrail("manager_tasks", "quant_operational_fly_command"), None
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
    # Job-Hunter: persistencia-only de tracking. Antes que INCOME_INJECTION para no forzar Tavily.
    if _is_job_hunter_worker(worker_id) and "job_opportunity_tracking" in (incoming or "").strip().lower():
        ctx = (incoming or "").strip()
        return format_guardrail("manager_tasks", "job_opportunity_tracking", context=ctx[:6000]), None
    # Job-Hunter: comando directo /job --add <url> en chat propio -> registrar/actualizar vacante (sin A2A).
    if _is_job_hunter_worker(worker_id) and _looks_like_job_add_command(incoming or ""):
        ctx = (incoming or "").strip()
        return format_guardrail("manager_tasks", "job_opportunity_tracking", context=ctx[:6000]), None
    # Job-Hunter: seguimiento de postulaciones en DuckDB (sin Tavily ni round-trip a Finanz).
    if _is_job_hunter_worker(worker_id) and _job_hunter_user_requests_application_tracking(incoming or ""):
        return load_guardrail("manager_tasks", "job_application_tracking"), None
    # Job-Hunter: evita run_sandbox con URLs inventadas; discovery = tavily_search.
    if _is_job_hunter_worker(worker_id) and job_hunter_user_requests_job_search(incoming):
        return load_guardrail("manager_tasks", "job_income_injection"), None
    # Intención DB/tablas/nombre → si el rol es personalizable, usar finanz (especialista) si está disponible
    is_db_intent = bool(
        _explicit_duckdb_schema_request
        or re.search(r"\b(db|esquema|schema|estructura|disponibles)\b", t)
        or ("nombre" in t and ("db" in t or "base" in t or "datos" in t))
    )
    if is_db_intent and (worker_id or "").strip().lower() == "personalizable":
        override = "finanz"  # invoke_worker lo usará si finanz está en list_workers

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
    if (worker_id or "").strip().lower() == "finanz" and _finanz_user_demands_tool_evidence_from_db(t):
        return f"{_FINANZ_TOOL_PRESSURE_TASK}\n\n--- Mensaje del usuario ---\n{text}", override
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


def _manager_greeting_fast_path_ok(incoming: str) -> bool:
    """Saludo corto sin comando fly: evita plan LLM y delegación al worker."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_simple_greeting

    return _is_simple_greeting(raw)


def _manager_capabilities_fast_path_ok(incoming: str) -> bool:
    """«Qué puedes hacer?» y similares: respuesta fija sin plan ni subagente."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_capabilities_smalltalk

    return _is_capabilities_smalltalk(raw)


def _greeting_fast_reply_text(worker_id: str | None) -> str:
    w = (worker_id or "").strip()
    wl = w.lower()
    if _is_job_hunter_worker(w):
        return (
            "Hola. Soy **OSINT JobHunter** (búsqueda y extracción de ofertas). "
            "Di rol, ubicación o remoto y, si quieres, portales (LinkedIn, Lever, etc.). "
            "Necesitas `/sandbox on` para ejecutar código en el contenedor browser."
        )
    if wl == "bi-analyst":
        return (
            "Hola. Soy tu analista de BI (DuckDB): consultas de solo lectura, esquema, métricas y gráficos cuando lo pidas. "
            "¿Qué quieres revisar?"
        )
    if w:
        return f"Hola. Aquí {w}. ¿En qué puedo ayudarte?"
    return "Hola. ¿En qué puedo ayudarte?"


def _capabilities_fast_reply_text(
    worker_id: str | None,
    *,
    coordinator_id: str | None = None,
    delegation_pool: list[str] | None = None,
) -> str:
    coord = (coordinator_id or "").strip()
    pool = [x for x in (delegation_pool or []) if (x or "").strip()]
    if coord and pool:
        lines = "\n".join(f"- {w}" for w in pool)
        return format_guardrail("capabilities", "axis_coordinator", coord=coord, lines=lines)
    w = (worker_id or "").strip()
    wl = w.lower()
    wl_norm = wl.replace("_", "-")
    if _is_job_hunter_worker(w):
        return load_guardrail("capabilities", "job_hunter")
    if wl == "bi-analyst":
        return load_guardrail("capabilities", "bi_analyst")
    if wl == "finanz":
        return load_guardrail("capabilities", "finanz")
    if wl in ("axis-maestro", "maestro") or wl_norm == "axis-maestro":
        sub = "\n".join(f"- {x}" for x in pool) if pool else (
            "- AXIS-Coder\n- AXIS-Mirror\n- AXIS-Radar\n- AXIS-Sentinel\n- AXIS-Phantom"
        )
        return format_guardrail("capabilities", "axis_maestro", sub=sub)
    if wl_norm == "siata-analyst":
        return load_guardrail("capabilities", "siata_analyst")
    if w:
        return format_guardrail("capabilities", "generic_worker", worker_id=w)
    return load_guardrail("capabilities", "default_fallback")


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
        _all_disk_r = list_workers(troot)
        # Multiplex Telegram (p. ej. /api/v1/telegram/pqrsd-assistant): el API Gateway
        # pasa entry_worker_id=PQRSD-Assistant. Antes solo se fusionaba en SYSTEM_EVENT
        # (TRADING_TICK, goals ticker); los mensajes normales quedaban con assigned=available[0]
        # (suele ser finanz) → delegación incorrecta. Si hay ruta HTTP, priorizar siempre ese worker.
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
        out["plan_attempt_index"] = 0
        out["plan_max_attempts"] = plan_max_attempts_from_env()
        out["plan_failure_reasons"] = []
        out["replan_requested"] = False
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
            reply = _capabilities_fast_reply_text(
                assigned, coordinator_id=coord, delegation_pool=pool
            )
            _audit_title = "Capacidades (respuesta directa)"
        else:
            log_sys(_obs, "Saludo: respuesta directa (sin plan ni subagente)")
            reply = _greeting_fast_reply_text(assigned)
            _audit_title = "Saludo directo"
        try:
            append_task_audit(
                db,
                chat_id,
                assigned or "manager",
                incoming,
                "SUCCESS",
                0,
                plan_title=_audit_title,
            )
        except Exception:
            pass
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
        """Formula un plan / tarea clara, genera plan_title/tasks y opcionalmente asigna finanz para intenciones DB/tablas."""
        _tid = (state.get("tenant_id") or "default").strip() or "default"
        _cid = (state.get("chat_id") or "").strip() or "unknown"
        set_log_context(
            tenant_id=_tid,
            worker_id="manager",
            chat_id=format_chat_log_identity(_cid, state.get("username")),
        )
        # Preservar incoming por si el estado no lo propaga (fallback: input, message)
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        available_plan = state.get("available_templates") or list_workers(troot)
        default_worker = available_plan[0] if available_plan else None
        assigned = (state.get("assigned_worker_id") or default_worker or "").strip() or default_worker
        coordinator_id = (state.get("coordinator_worker_id") or "").strip() or None
        delegation_pool = [str(x).strip() for x in (state.get("delegation_pool") or []) if str(x).strip()]
        if not incoming:
            _log.warning("manager plan: incoming vacío en state (keys=%s)", list(state.keys()))

        _hrp_fast: tuple[str, list[str], str, str] | None = None
        _orch_affirm: tuple[str, list[str], str, str] | None = None
        _visual_fast: tuple[str, list[str], str, str] | None = None
        _url_fast: tuple[str, list[str], str, str] | None = None
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
            _hrp_fast = _try_quant_hrp_affirm_followup(
                incoming,
                state.get("history"),
                assigned,
                _tid,
                [str(x) for x in (available_plan or []) if x],
            )
        if incoming and not _orch_affirm and not _hrp_fast:
            _visual_fast = _try_visual_generation_fast_plan(
                incoming,
                [str(x) for x in (available_plan or []) if x],
            )
        if incoming and not _orch_affirm and not _hrp_fast and not _visual_fast:
            _url_fast = _try_quant_url_research_fast_plan(
                incoming,
                [str(x) for x in (available_plan or []) if x],
            )
        if _orch_affirm:
            plan_title, tasks, _inject_orch, _ov_orch = _orch_affirm
            mercenary_spec = None
        elif _hrp_fast:
            plan_title, tasks, _inject_hrp, _ov_hrp = _hrp_fast
            mercenary_spec = None
        elif _visual_fast:
            plan_title, tasks, _inject_vis, _ov_vis = _visual_fast
            mercenary_spec = None
        elif _url_fast:
            plan_title, tasks, _inject_url, _ov_url = _url_fast
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

            plan_title = _sanitize_finanz_manager_plan_title(plan_title, incoming, assigned)

        is_job_add_command = _looks_like_job_add_command(incoming)
        _plan_chat_id = (state.get("chat_id") or "").strip() or None
        if is_job_add_command and mercenary_spec is not None:
            # /job --add nunca debe salir por mercenario; forzar flujo normal de tracking.
            mercenary_spec = None
        if mercenary_spec is not None and _should_disable_mercenary_for_browser_intent(
            incoming, tasks, plan_title, chat_id=_plan_chat_id
        ):
            mercenary_spec = None
        if mercenary_spec is not None and _should_disable_mercenary_for_quant_signal_intent(
            incoming, assigned
        ):
            mercenary_spec = None
        elif mercenary_spec is not None and _should_disable_mercenary_for_quant_lone_https_url(
            incoming, assigned
        ):
            mercenary_spec = None
        elif mercenary_spec is not None and _should_disable_mercenary_for_quant_external_research(
            incoming, assigned, tasks, plan_title
        ):
            mercenary_spec = None

        # Prioridad A2A: en crisis de caja + intención laboral, enrutar a JobHunter si está disponible.
        job_hunter_in_team = _pick_job_hunter_worker(list(available_plan or []))
        cashflow_job_intent = _user_signals_cashflow_stress(incoming) or job_hunter_user_requests_job_search(incoming)
        if job_hunter_in_team and (cashflow_job_intent or is_job_add_command) and not _orch_affirm and not _hrp_fast and not _visual_fast and not _url_fast:
            assigned = job_hunter_in_team

        # Mantener lógica existente de ruteo / planned_task
        if _orch_affirm:
            if _ov_orch and _ov_orch in (available_plan or []):
                assigned = _ov_orch
            override_worker = _ov_orch
            planned = _inject_orch
            planned_final = _inject_orch
        elif _hrp_fast:
            if _ov_hrp and _ov_hrp in (available_plan or []):
                assigned = _ov_hrp
            override_worker = _ov_hrp
            planned = _inject_hrp
            planned_final = _inject_hrp
        elif _visual_fast:
            if _ov_vis and _ov_vis in (available_plan or []):
                assigned = _ov_vis
            override_worker = _ov_vis
            planned = _inject_vis
            planned_final = _inject_vis
        elif _url_fast:
            if _ov_url and _ov_url in (available_plan or []):
                assigned = _ov_url
            override_worker = _ov_url
            planned = _inject_url
            planned_final = _inject_url
        else:
            planned, override_worker = _plan_task(incoming, assigned)
            planned_final = planned or incoming
        _pa_plan = int(state.get("plan_attempt_index") or 0)
        _max_plan = int(state.get("plan_max_attempts") or plan_max_attempts_from_env())
        if replan_enabled() and _pa_plan > 0:
            planned_final = (planned_final or "").strip() + format_replan_task_suffix(_pa_plan, _max_plan)

        if coordinator_id and delegation_pool and not _orch_affirm and not _hrp_fast and not _visual_fast and not _url_fast:
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

        handoff_context: dict[str, Any] | None = None
        active_mission: dict[str, Any] | None = None
        # A2A con retorno a Finanz solo si Finanz está en el equipo; si no, Job-Hunter cierra el turno solo (evita handoff fantasma).
        finanz_in_team = _finanz_worker_in_templates(list(available_plan or []))
        if job_hunter_in_team and cashflow_job_intent and finanz_in_team and not is_job_add_command:
            active_mission = {
                "source_worker": "finanz",
                "target_worker": "job_hunter",
                "mission": "INCOME_INJECTION",
                "urgency": "high",
            }
            handoff_context = dict(active_mission)

        out: ManagerAgentState = {
            "planned_task": planned_final,
            "incoming": incoming,
            "task_summary": task_summary,
            "plan_title": plan_title or None,
            "tasks": tasks or [],
            "replan_requested": False,
        }  # type: ignore[assignment]
        if mercenary_spec:
            out["mercenary_spec"] = mercenary_spec
        if handoff_context:
            out["handoff_context"] = handoff_context
        if active_mission:
            out["active_mission"] = active_mission

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
            _all_plan_disk = list_workers(troot)
            _canon_re = _resolve_template_id(_all_plan_disk, route_entry)
            if _canon_re and _canon_re in _all_plan_disk:
                out["assigned_worker_id"] = _canon_re
                if _canon_re not in available_plan:
                    available_plan = list(available_plan) + [_canon_re]

        if _strip_mercenary_spec_for_browser_worker(out, troot):
            mercenary_spec = None

        if mercenary_spec is None and _should_disable_mercenary_for_quant_signal_intent(
            incoming, out.get("assigned_worker_id")
        ):
            pass

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
        plan_for_task = (plan_title or "").strip()
        if plan_for_task:
            # Mostrar únicamente el título del plan en /tasks (sin corchetes)
            activity_task = plan_for_task
        else:
            activity_task = task_summary
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
        tenant_id = state.get("tenant_id") or "default"
        user_id = state.get("user_id") or chat_id or "default"
        vault_db_path = (state.get("vault_db_path") or "").strip()
        shared_db_path = (state.get("shared_db_path") or "").strip()
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        planned_task = (state.get("planned_task") or "").strip() or incoming
        plan_title = (state.get("plan_title") or "").strip() or None
        history = state.get("history") or []
        available = list(state.get("available_templates") or list_workers(troot))
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        _all_iw = list_workers(troot)
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
        _combined = planned_task or incoming
        _lite_stdio_mcp = _worker_should_use_lite_stdio_mcp_surface(_combined)
        _url_research_mcp = _worker_should_use_url_research_mcp_surface(_combined)
        _visual_lite_mcp = _manager_visual_generation_intent(_combined) and _worker_matches_id(
            assigned, "quant_trader"
        )
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
        max_a = int(state.get("plan_max_attempts") or plan_max_attempts_from_env())
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
            from duckclaw.workers.factory import _agent_debug_log, _get_db_path, _same_duckdb_file
            from duckclaw.workers.manifest import load_manifest

            spec_inv = load_manifest(assigned, troot)
            mgr_path = str(getattr(db, "_path", "") or "").strip()
            worker_resolved = _get_db_path(
                assigned, tenant_id, (vault_db_path or db_path or None)
            ).strip()
            _mgr_read_only = bool(getattr(db, "_read_only", False))
            mgr_con_is_none = getattr(db, "_con", None) is None and getattr(db, "_native", None) is None
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
            cache_hit = worker_cache_key in _worker_graph_cache
            # #region agent log
            _agent_debug_log(
                "manager_graph.py:invoke_worker_node:pre_suspend",
                "worker_db_paths",
                {
                    "assigned": assigned,
                    "mgr_path_tail": mgr_path[-96:] if mgr_path else "",
                    "worker_resolved_tail": worker_resolved[-96:] if worker_resolved else "",
                    "hub_same_as_worker": _hub_same_as_worker,
                    "mgr_read_only": _mgr_read_only,
                    "needs_rw_vault": _needs_rw_vault,
                    "suspend_for_rw_worker": _suspend_for_rw_worker,
                    "will_suspend_ro": _will_suspend_ro,
                    "will_skip_private": _will_skip_private,
                    "mgr_con_is_none": mgr_con_is_none,
                    "cache_hit": cache_hit,
                    "spawn_inline_writes": _spawn_inline_writes,
                    "summarize_vault_ro": bool(_summarize_vault_ro),
                },
                "A",
            )
            # #endregion
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
                # #region agent log
                _agent_debug_log(
                    "manager_graph.py:invoke_worker_node:post_suspend",
                    "manager_handle_after_suspend",
                    {
                        "assigned": assigned,
                        "mgr_con_is_none": getattr(db, "_con", None) is None
                        and getattr(db, "_native", None) is None,
                    },
                    "A",
                )
                # #endregion
            if _visual_lite_mcp:
                try:
                    from duckclaw.forge.skills.visual_state_delta import set_visual_state_delta_hub_db

                    set_visual_state_delta_hub_db(db)
                except Exception:
                    pass
            if worker_cache_key not in _worker_graph_cache:
                # #region agent log
                _agent_debug_log(
                    "manager_graph.py:invoke_worker_node:pre_build_worker_graph",
                    "build_worker_graph_call",
                    {
                        "assigned": assigned,
                        "reuse_db_same_object": True,
                        "vault_arg_tail": str(vault_db_path or db_path or "")[-96:],
                    },
                    "B",
                )
                # #endregion
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
            worker_state = {
                "input": planned_task,
                "incoming": planned_task,
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
            worker_invoke = worker_graph.invoke(worker_state, trace_cfg)
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
                elif (assigned or "").strip() == "PQRSD-Assistant":
                    try:
                        from duckclaw.forge.atoms.pqrsd_registration_egress_guard import (
                            pqrsd_persist_tool_used,
                            pqrsd_reply_claims_internal_registration,
                        )

                        _pqrsd_replan = pqrsd_reply_claims_internal_registration(
                            raw_worker_reply
                        ) and not pqrsd_persist_tool_used(_tools_list)
                    except Exception:
                        _pqrsd_replan = False
                    if _pqrsd_replan:
                        _rp = "pqrsd: radicación afirmada sin admin_sql ni pqrsd_registrar_radicacion_crm"
                        reasons_acc = merge_failure_reasons(reasons_acc, _rp)
                        if pa + 1 < max_a:
                            replan_after = True
                            next_plan_attempt = pa + 1
                            log_sys(
                                _obs,
                                "manager replan: PQRSD sin persist -> intento %s/%s",
                                pa + 2,
                                max_a,
                            )
                        else:
                            exhausted_final = True
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
            # DuckDB: un worker RW (p. ej. finanz) no debe dejar el .duckdb abierto en caché cuando el manager
            # no pasó por suspend RO (hub vs vault distinto en path); si no, db-writer y task_audit_log pierden lock
            # (evidencia 2026-05-12: IO Error finanzdb1 durante append_task_audit).
            _worker_rw = _wdb is not None and not bool(getattr(_wdb, "_read_only", False))
            _wdb_same_as_mgr = _wdb is not None and _wdb is db
            # #region agent log
            try:
                from duckclaw.workers.factory import _agent_debug_log as _mgr_dbg

                _mgr_dbg(
                    "manager_graph.py:invoke_worker_node:finally",
                    "worker_db_cleanup",
                    {
                        "assigned": assigned,
                        "wdb_is_none": _wdb is None,
                        "wdb_same_as_mgr": _wdb_same_as_mgr,
                        "worker_rw": _worker_rw,
                        "suspend_for_rw_worker": _suspend_for_rw_worker,
                        "will_suspend_ro": _will_suspend_ro,
                        "mgr_con_is_none_before_close": getattr(db, "_con", None) is None
                        and getattr(db, "_native", None) is None,
                    },
                    "C",
                )
            except Exception:
                pass
            # #endregion
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
        if replan_after:
            out["replan_requested"] = True
            out["plan_attempt_index"] = next_plan_attempt
            out["plan_failure_reasons"] = reasons_acc
        elif exhausted_final:
            out["replan_requested"] = False
            out["plan_attempt_index"] = max_a
            out["plan_failure_reasons"] = reasons_acc
        else:
            out["replan_requested"] = False
            out["plan_attempt_index"] = 0
            out["plan_failure_reasons"] = []
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
        raw_reply = state.get("last_worker_raw_reply") or state.get("reply") or ""
        if _worker_matches_id(current_worker, "finanz") and _contains_job_opportunity_tracking_request(
            raw_reply
        ):
            return "handoff_job_track"
        if _worker_matches_id(current_worker, "finanz") and _contains_income_injection_request(raw_reply):
            return "handoff_to_target"
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

    def handoff_to_target_node(state: ManagerAgentState) -> ManagerAgentState:
        available = state.get("available_templates") or []
        target_worker = _pick_job_hunter_worker(list(available or [])) or "job_hunter"
        active_mission = {
            "source_worker": "finanz",
            "target_worker": target_worker,
            "mission": "INCOME_INJECTION",
            "urgency": "high",
        }
        mission_task, _ = _plan_task(
            load_guardrail("manager_tasks", "job_income_injection"),
            target_worker,
        )
        out: ManagerAgentState = {
            "assigned_worker_id": target_worker,
            "planned_task": mission_task,
            "incoming": mission_task,
            "input": mission_task,
            "active_mission": active_mission,
            "handoff_context": dict(active_mission),
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
        if "plan_title" in state:
            out["plan_title"] = state["plan_title"]
        if "tasks" in state:
            out["tasks"] = state["tasks"]
        if "task_summary" in state:
            out["task_summary"] = state["task_summary"]
        _tok_ht = (state.get("outbound_telegram_bot_token") or "").strip()
        if _tok_ht:
            out["outbound_telegram_bot_token"] = _tok_ht
        return out

    def handoff_job_track_node(state: ManagerAgentState) -> ManagerAgentState:
        """A2A: Finanz solicitó persistencia de vacante vía JobHunter (tabla job_opportunities)."""
        available = state.get("available_templates") or []
        target_worker = _pick_job_hunter_worker(list(available or [])) or "job_hunter"
        user_ctx = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        synthetic = f"TAREA: JOB_OPPORTUNITY_TRACKING.\n{user_ctx}"
        mission_task, _ = _plan_task(synthetic, target_worker)
        active_mission = {
            "source_worker": "finanz",
            "target_worker": target_worker,
            "mission": "JOB_OPPORTUNITY_TRACKING",
            "urgency": "medium",
        }
        out: ManagerAgentState = {
            "assigned_worker_id": target_worker,
            "planned_task": mission_task,
            "incoming": mission_task,
            "input": mission_task,
            "active_mission": active_mission,
            "handoff_context": dict(active_mission),
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
        if "plan_title" in state:
            out["plan_title"] = state["plan_title"]
        if "tasks" in state:
            out["tasks"] = state["tasks"]
        if "task_summary" in state:
            out["task_summary"] = state["task_summary"]
        _tok_hj = (state.get("outbound_telegram_bot_token") or "").strip()
        if _tok_hj:
            out["outbound_telegram_bot_token"] = _tok_hj
        return out

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

        raw_job_hunter_reply = (state.get("last_worker_raw_reply") or state.get("reply") or "").strip()
        mission_name = (mission.get("mission") or "INCOME_INJECTION").strip() or "INCOME_INJECTION"
        if mission_name.upper() == "JOB_OPPORTUNITY_TRACKING":
            mission_system_message = (
                f"JobHunter completó la misión {mission_name}. "
                f"Resultado (persistencia / SQL): {raw_job_hunter_reply}\n\n"
                "Confirma al usuario el registro de la vacante o postulación de forma breve."
            )
            synthesis_task = load_guardrail("manager_tasks", "job_track_synthesis_finanz")
        else:
            mission_system_message = (
                f"JobHunter ha completado la misión {mission_name}. "
                f"Aquí están los resultados crudos: {raw_job_hunter_reply}\n\n"
                "Sintetiza esto en tu reporte financiero final."
            )
            synthesis_task = load_guardrail("manager_tasks", "job_income_synthesis_finanz")

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
    graph.add_node("handoff_to_target", handoff_to_target_node)
    graph.add_node("handoff_job_track", handoff_job_track_node)
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
            "handoff_to_target": "handoff_to_target",
            "handoff_job_track": "handoff_job_track",
            "plan": "plan",
            "end": END,
        },
    )
    graph.add_edge("return_to_source", "invoke_worker")
    graph.add_edge("handoff_to_target", "invoke_worker")
    graph.add_edge("handoff_job_track", "invoke_worker")
    return graph.compile()
