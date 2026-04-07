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
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from duckclaw.forge.atoms.state import ManagerAgentState
from duckclaw.graphs.sandbox import (
    extract_latest_sandbox_document_paths,
    extract_latest_sandbox_figure_base64,
    extract_latest_sandbox_figures_base64,
)
from duckclaw.graphs.subagent_run_id import acquire_subagent_slot, release_subagent_slot
from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_plan, log_sys, set_log_context

_log = logging.getLogger(__name__)
_obs = get_obs_logger()
_worker_graph_cache: dict[str, Any] = {}


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


def clear_worker_graph_cache() -> None:
    """
    Los grafos de worker cierran sobre un DuckClaw concreto; tras cerrar la conexión del manager
    hay que vaciar la caché para no reutilizar handles muertos en la siguiente petición.
    """
    global _worker_graph_cache
    _worker_graph_cache.clear()


def _agent_config_db_for_vault(hub_db: Any, vault_db_path: str | None) -> Any:
    """
    Lee claves por chat (team_templates, sandbox_enabled, llm_*) desde el vault del tenant
    cuando existe; si no, desde el hub ``hub_db``. Evita mezclar equipo Finanz/Job-Hunter del
    hub multiplex con bots SIATA u otros que comparten chat_id pero usan otro .duckdb.
    """
    vp = (vault_db_path or "").strip()
    if vp and vp != ":memory:":
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


def job_hunter_user_requests_job_search(incoming: str) -> bool:
    """
    True si el texto del usuario (o la TAREA inyectada) implica búsqueda de empleo con acción concreta.
    Usado por el planner del manager y por el worker (forzar tavily_search en el primer turno).
    """
    raw = (incoming or "").strip()
    if not raw:
        return False
    t = raw.lower()
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
    return any(x in t for x in job_terms) and (
        any(x in t for x in action_terms) or "http" in t or "www." in t
    )


def _user_signals_cashflow_stress(incoming: str) -> bool:
    """Detecta estrés de caja / iliquidez en español coloquial."""
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
        "deudas",
        "deuda",
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


def _prepend_subagent_label_once(reply: str, label: str) -> str:
    """
    Añade el encabezado del subagente solo si el texto aún no lo trae al inicio.
    Evita respuestas con doble prefijo como:
    `finanz 1` + `finanz 1`.
    """
    clean_reply = _strip_leading_subagent_instance_headers(reply or "")
    clean_label = (label or "").strip()
    if not clean_label or not clean_reply:
        return clean_reply
    # Tolerar un prefijo markdown básico (`**label**`) además del plano.
    if clean_reply.startswith(clean_label):
        return clean_reply
    if clean_reply.startswith(f"**{clean_label}**"):
        return clean_reply
    return f"{clean_label}\n\n{clean_reply}"


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
    # Gateway (Telegram /context): el cuerpo puede mencionar DuckDB, "estructura", "schema", tablas, etc.
    # Sin este bypass, _plan_task sustituye el mensaje por TAREA: listar tablas y el worker pierde la directiva.
    if text.startswith("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]") or text.startswith(
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"
    ):
        return text, None
    if "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in text or "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in text:
        # Directiva no al inicio (p. ej. prefijo invisible): devolver el texto completo tal cual llegó al manager.
        return (incoming or "").strip(), None
    # /context --add + foto: VLM antepone «Usuario dice:…»; evitar heurísticas db/tablas (p. ej. nombre+datos).
    if "[VLM_CONTEXT" in text and "Contexto visual adjunto:" in text:
        tctx = text.lower()
        if "/context" in tctx and "--add" in tctx:
            return (incoming or "").strip(), None
    t = text.lower()
    override: Optional[str] = None
    # MVP Leila: saludos cortos → respuesta de tienda (evita tono “agente de investigación”).
    if (worker_id or "").strip() == "LeilaAssistant":
        plain = (incoming or "").strip()
        if len(plain) <= 24 and re.match(
            r"^(hola|hey|hi|hello|buen(as?|os)\s*(días|dias|tardes|noches)?|qué\s+tal|que\s+tal)[\s!?.¡¿]*$",
            plain.lower(),
        ):
            return (
                "TAREA: El cliente saluda. Preséntate en 2–3 frases como Leila Store (tienda de ropa): "
                "tono cálido y directo. Menciona /catalogo para ver productos y /pedido <id> <talla> para pedir. "
                "No digas que eres un agente de investigación ni listes herramientas genéricas.",
                None,
            )
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
            return (
                "TAREA: El usuario pregunta qué puedes hacer o pide presentarte. "
                "Responde en español como **analista de datos / BI** sobre la base DuckDB (esquema analítico): "
                "consultas SQL de solo lectura, get_schema_info, explain_sql, sandbox para gráficos cuando aplique. "
                "Sé breve y concreto. **Prohibido:** usar la frase «Agente de Investigación Activa», hablar de "
                "investigación web genérica o presentarte como asistente de investigación abstracto.",
                None,
            )
    # Job-Hunter: persistencia-only (A2A desde Finanz). Antes que INCOME_INJECTION para no forzar Tavily.
    if _is_job_hunter_worker(worker_id) and "job_opportunity_tracking" in (incoming or "").strip().lower():
        ctx = (incoming or "").strip()
        return (
            "TAREA: Misión A2A JOB_OPPORTUNITY_TRACKING. Registra en finance_worker.job_opportunities la vacante o "
            "postulación del contexto siguiente. **No** uses tavily_search ni run_browser_sandbox salvo que no exista "
            "ninguna URL ni dato mínimo de oferta en el contexto. Usa read_sql/admin_sql: INSERT con apply_url (literal del "
            "mensaje si existe), title, company, location según el texto; status='applied' si el usuario indica que ya postuló, "
            "si no 'tracking'; notes con detalle breve; applied_at=CURRENT_TIMESTAMP cuando aplique a aplicación ya hecha. "
            "Si INSERT falla por URL duplicada (índice único), lee la fila y haz UPDATE de status/notes/applied_at.\n\n"
            f"--- Contexto ---\n{ctx[:6000]}",
            None,
        )
    # Job-Hunter: seguimiento de postulaciones en DuckDB (sin Tavily ni round-trip a Finanz).
    if _is_job_hunter_worker(worker_id) and _job_hunter_user_requests_application_tracking(incoming or ""):
        return (
            "TAREA: El usuario pide seguimiento de vacantes/postulaciones **ya registradas** en la base local. "
            "Ejecuta read_sql sobre finance_worker.job_opportunities (p. ej. ORDER BY COALESCE(applied_at, updated_at) DESC LIMIT 30) "
            "y responde en español de forma **completa pero concisa**: tabla o lista con title, company, status, apply_url, fechas; "
            "si no hay filas, dilo y ofrece registrar con la URL de la oferta. "
            "**Prohibido** tavily_search y run_browser_sandbox en este turno (no es búsqueda de ofertas nuevas).",
            None,
        )
    # Job-Hunter: evita run_sandbox con URLs inventadas; discovery = tavily_search.
    if _is_job_hunter_worker(worker_id) and job_hunter_user_requests_job_search(incoming):
        return (
            "TAREA: Misión A2A INCOME_INJECTION. El usuario pide búsqueda de empleo y/o enlaces para postular. "
            "Sigue el **Flujo cognitivo** del system prompt: (1) **`tavily_search` SIEMPRE primero** — "
            "prohibido anticipar fallo del sandbox o negar la búsqueda antes del resultado `tool` de Tavily; "
            "(2) luego intenta **`run_browser_sandbox`** si aplica; "
            "(3) si el sandbox falla, ve directo al egress con **datos crudos ya obtenidos de Tavily** (no simules otra discovery). "
            "**Entrega hasta 3 vacantes accionables** con rol, modalidad, rango (si existe), fit y **enlace literal** verificado. "
            "Prioriza contratación rápida/freelance y no uses `run_sandbox` solo para listas fijas de portales.",
            None,
        )
    # Intención DB/tablas/nombre → si el rol es personalizable, usar finanz (especialista) si está disponible
    is_db_intent = (
        re.search(r"\b(nombre\s+de\s+la\s+db|db|tablas?|tables?|esquema|schema|estructura|disponibles)\b", t)
        or "tablas" in t
        or ("nombre" in t and ("db" in t or "base" in t or "datos" in t))
    )
    if is_db_intent and (worker_id or "").strip().lower() == "personalizable":
        override = "finanz"  # invoke_worker lo usará si finanz está en list_workers

    # Última partida / partida más reciente
    is_latest_game_intent = bool(
        re.search(
            r"\b(ultima|última|mas\s+reciente|más\s+reciente)\s+partida\b",
            t,
        )
    ) or ("partida" in t and ("ultima" in t or "última" in t or "reciente" in t))
    if is_latest_game_intent:
        task = (
            "TAREA: El usuario quiere conocer la última partida de The Mind. "
            "Ejecuta read_sql con una consulta directa sobre the_mind_games para traer solo 1 registro "
            "(prioriza ORDER BY game_id DESC LIMIT 1, o por created_at si esa columna existe). "
            "Si la consulta falla por columna inexistente, corrige automáticamente y reintenta sin preguntar. "
            "Responde con game_id, status, current_level, lives y shurikens."
        )
        return task, override

    # Nombre de la db / base de datos
    if re.search(r"\b(nombre\s+de\s+la\s+db|nombre\s+db|cual\s+es\s+el\s+nombre|nombre\s+de\s+la\s+base)\b", t) or (
        "nombre" in t and ("db" in t or "base" in t or "datos" in t)
    ):
        task = (
            "TAREA: El usuario quiere saber qué base de datos se está usando. "
            "Ejecuta get_db_path y responde de forma proactiva: indica la db usada en texto plano (sin comillas ni negrita). En el cierre invita a /team, /tasks, /help y a crear objetivos con /goals (por defecto están vacíos). Usa 1-2 emojis si encaja."
        )
        return task, override
    # Contenido de una tabla concreta
    is_table_content_intent = bool(
        re.search(
            r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|contenido\s+de\s+la\s+tabla|"
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
            task = (
                "TAREA: El usuario quiere ver el contenido de una tabla específica. "
                f"Ejecuta read_sql con SELECT * FROM {table_name} LIMIT 20. "
                "Si falla por nombre/esquema, corrige al esquema válido sin pedir aclaración innecesaria. "
                "Explica brevemente las columnas visibles y ofrece profundizar con filtros."
            )
            return task, override

        task = (
            "TAREA: El usuario quiere ver el contenido de una tabla específica. "
            "Ejecuta read_sql con SELECT * FROM <tabla> LIMIT 20 (o una consulta equivalente segura), "
            "explica brevemente las columnas visibles y ofrece profundizar con filtros."
        )
        return task, override

    # Tablas / esquema / estructura
    if re.search(
        r"\b(tablas?|tables?|esquema|schema|estructura|listar\s+tablas|disponibles)\b",
        t,
    ) or "tablas" in t or "qué tablas" in t or "que tablas" in t:
        task = (
            "TAREA: El usuario quiere ver las tablas de la base de datos. "
            "Ejecuta read_sql con SHOW TABLES o SELECT desde information_schema.tables y responde con la lista de tablas. En el cierre invita a /team, /tasks, /help y a crear objetivos con /goals."
        )
        return task, override
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
            "Síntesis de contexto (recién inyectado)",
            [
                "Resumir solo el bloque del usuario en bullets técnicos alineados al worker.",
                "No ejecutar inspect_schema ni read_sql salvo que el usuario lo pida explícitamente aparte.",
            ],
        )
    if text.startswith("[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"):
        return (
            "Síntesis de contexto almacenado",
            [
                "Resumir solo el volcado de main.semantic_memory en bullets técnicos.",
                "No listar tablas ni inspeccionar esquema: el texto ya está en el mensaje.",
            ],
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


def _coerce_planner_payload(data: Any) -> tuple[str, list[str], dict[str, Any] | None]:
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

    return str(title).strip(), tasks_list, merc_obj


def _llm_plan_from_model(
    llm: Any, incoming: str, planner_system_prompt: str
) -> Optional[tuple[str, list[str], dict[str, Any] | None]]:
    """
    Invoca el LLM del Manager para obtener {"plan_title", "tasks", "mercenary"?}.
    Devuelve None si falla el invoke, el parse o el contrato (el caller usa heurística).
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    append = (os.environ.get("DUCKCLAW_MANAGER_PLANNER_SYSTEM_APPEND") or "").strip()
    system_chunks = [planner_system_prompt.strip(), append]
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
        title, tasks, mercenary_spec = _coerce_planner_payload(data)
    except ValueError as exc:
        _log.debug("manager planner: invalid payload: %s", exc)
        return None
    title = _truncate_plan_title_words(title, 5)
    if not title:
        return None
    if not tasks:
        clip = (incoming or "").strip()[:200]
        tasks = [f"Resolver la solicitud del usuario: {clip}" if clip else "Resolver solicitud del usuario"]
    return title, tasks, mercenary_spec


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
    if wl == "leilaassistant":
        return (
            "Hola. ¿En qué puedo ayudarte? Puedes ver /catalogo o pedir con /pedido."
        )
    if w:
        return f"Hola. Aquí {w}. ¿En qué puedo ayudarte?"
    return "Hola. ¿En qué puedo ayudarte?"


def _capabilities_fast_reply_text(worker_id: str | None) -> str:
    w = (worker_id or "").strip()
    wl = w.lower()
    wl_norm = wl.replace("_", "-")
    if _is_job_hunter_worker(w):
        return (
            "Soy **OSINT JobHunter** (empleo / OSINT). Puedo:\n"
            "• **Discovery:** búsqueda amplia con Tavily (consultas tipo Google Dork; URLs limpias, sin HTML en el chat).\n"
            "• **Extracción:** navegación pesada en sandbox de navegador (Playwright en contenedor) y resultado en Parquet.\n"
            "• **Ingesta:** cargar ofertas en DuckDB (`finance_worker.job_opportunities`) con SQL.\n"
            "• **Resumen:** hasta **3 vacantes** con descripción breve y **enlace verificado** para postular (Tavily + opcional Playwright en sandbox).\n\n"
            "Ejemplos: «Busca data scientist remoto Colombia y LinkedIn», "
            "«Ofertas de backend en Lever/Greenhouse, Europa». "
            "Imagen Docker: `docker build -t duckclaw/browser-env:latest docker/browser-env/`. "
            "`/sandbox on` para ejecutar código en contenedor."
        )
    if wl == "bi-analyst":
        return (
            "Puedo trabajar con tu DuckDB en solo lectura: esquema y tablas, consultas SQL, "
            "métricas, tendencias y gráficos en sandbox. "
            "Ejemplo de petición: «¿Cuántas filas tiene la tabla sales?» o «Resume ventas por día». "
            "Dime qué quieres medir o qué tabla explorar."
        )
    if wl == "finanz":
        return (
            "Soy **Finanz** (finanzas personales + broker). Puedo:\n"
            "• **Cuentas en DuckDB:** saldos por cuenta (Bancolombia, Nequi, efectivo…), "
            "resumen con **totales por moneda**, gastos, presupuestos y deudas.\n"
            "• **IBKR:** consultar saldo y portafolio en vivo con la API del gateway cuando lo pidas "
            "(o en resúmenes amplios junto a tus cuentas locales).\n"
            "• **Datos y cambios:** consultas `read_sql`, registro con las tools de finanzas, "
            "y actualizaciones de saldo vía `admin_sql` (cola db-writer).\n"
            "• **Mercado / cuant:** OHLCV, CFD y contexto web cuando el manifest lo tenga activo.\n\n"
            "Ejemplos: «Dame un resumen de mis cuentas», «¿Cuánto tengo en Nequi?», "
            "«Consulta el saldo de IBKR», «gastos del mes»."
        )
    if wl == "leilaassistant":
        return (
            "Puedo ayudarte con el catálogo, pedidos (/pedido) y dudas sobre productos. "
            "Prueba /catalogo o escribe qué buscas."
        )
    if wl_norm == "siata-analyst":
        return (
            "Soy **SIATA-Analyst** y trabajo con datos ambientales oficiales para Medellín y el Valle de Aburrá. "
            "Puedo ayudarte con:\n"
            "• **Calidad del aire:** PM2.5 (y PM10 cuando esté disponible).\n"
            "• **Lluvia y pluviómetros:** lectura y tendencias recientes.\n"
            "• **Niveles de quebradas:** estado reportado y cambios observables.\n"
            "• **Radar SIATA:** último producto publicado (archivo, hora local/UTC y enlace).\n"
            "• **Análisis técnico:** consultas con `read_sql` y apoyo en `run_sandbox` cuando se necesite procesar más detalle.\n\n"
            "Ejemplos: «¿Cuál es el último dato del radar?», "
            "«¿Cómo está el PM2.5 hoy?», «¿Qué muestran las quebradas ahora?»."
        )
    if w:
        return (
            f"Actúo como asistente ({w}): describe la tarea o el dato que necesitas y la encaminamos."
        )
    return "Describe qué necesitas (datos, consulta o objetivo) y te indico los siguientes pasos."


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
        out = {"assigned_worker_id": assigned, "available_templates": available}
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
        if _manager_capabilities_fast_path_ok(incoming):
            log_sys(_obs, "Capacidades: respuesta directa (sin plan ni subagente)")
            reply = _capabilities_fast_reply_text(assigned)
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
        if not incoming:
            _log.warning("manager plan: incoming vacío en state (keys=%s)", list(state.keys()))

        _psp = (planner_system_prompt or "").strip()
        mercenary_spec: dict[str, Any] | None = None
        if llm is not None and _psp:
            _parsed = _llm_plan_from_model(llm, incoming, _psp)
            if _parsed:
                plan_title, tasks, mercenary_spec = _parsed
            else:
                plan_title, tasks = _llm_plan(incoming)
                mercenary_spec = None
        else:
            plan_title, tasks = _llm_plan(incoming)
            mercenary_spec = None

        # Prioridad A2A: en crisis de caja + intención laboral, enrutar a JobHunter si está disponible.
        job_hunter_in_team = _pick_job_hunter_worker(list(available_plan or []))
        cashflow_job_intent = _user_signals_cashflow_stress(incoming) or job_hunter_user_requests_job_search(incoming)
        if job_hunter_in_team and cashflow_job_intent:
            assigned = job_hunter_in_team

        # Mantener lógica existente de ruteo / planned_task
        planned, override_worker = _plan_task(incoming, assigned)
        planned_final = planned or incoming

        # Derivar task_summary a partir del mensaje original / planned_task
        task_summary = _task_summary_for_activity(incoming, planned_final)

        handoff_context: dict[str, Any] | None = None
        active_mission: dict[str, Any] | None = None
        # A2A con retorno a Finanz solo si Finanz está en el equipo; si no, Job-Hunter cierra el turno solo (evita handoff fantasma).
        finanz_in_team = _finanz_worker_in_templates(list(available_plan or []))
        if job_hunter_in_team and cashflow_job_intent and finanz_in_team:
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
        }  # type: ignore[assignment]
        if mercenary_spec:
            out["mercenary_spec"] = mercenary_spec
        if handoff_context:
            out["handoff_context"] = handoff_context
        if active_mission:
            out["active_mission"] = active_mission

        if override_worker and override_worker in available_plan:
            out["assigned_worker_id"] = override_worker
        elif assigned not in available_plan and available_plan:
            out["assigned_worker_id"] = available_plan[0]
        else:
            out["assigned_worker_id"] = assigned

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
        available = state.get("available_templates") or list_workers(troot)
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        if assigned not in available:
            assigned = available[0] if available else None
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
        try:
            global _worker_graph_cache
            slot_token, run_label_n = acquire_subagent_slot(tenant_id, assigned, str(chat_id or ""))
            agent_instance_label = f"{assigned} {run_label_n}".strip()
            worker_cache_key = (
                f"{tenant_id}::{assigned}::{vault_db_path or db_path or ''}::{shared_db_path}"
                f"::{(llm_provider or '').strip()}::{(llm_model or '').strip()}::{(llm_base_url or '').strip()}"
            )
            from duckclaw.workers.factory import _same_duckdb_file
            from duckclaw.workers.manifest import load_manifest

            spec_inv = load_manifest(assigned, troot)
            vault_eff = (vault_db_path or db_path or "").strip()
            mgr_path = str(getattr(db, "_path", "") or "").strip()
            # DuckDB: no RO+RW simultáneo al mismo archivo. Suspender el RO del manager antes
            # de abrir el worker RW; leer sandbox/chat_state antes (sin worker RW abierto).
            _suspend_for_rw_worker = bool(
                getattr(db, "_read_only", False)
                and not spec_inv.read_only
                and vault_eff
                and mgr_path
                and _same_duckdb_file(mgr_path, vault_eff)
            )
            _cfg_db = _agent_config_db_for_vault(db, vault_db_path or None)
            raw_sb = get_chat_state(_cfg_db, chat_id, "sandbox_enabled")
            sb_on = (raw_sb or "").strip().lower() in ("true", "1", "on", "sí", "si")
            db_display = vault_db_path or db_path or "(unknown)"
            if _suspend_for_rw_worker:
                db.suspend_readonly_file_handle()
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
                schedule_chat_heartbeat_dm,
            )

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
                str(chat_id or "").strip(),
                str(user_id or "").strip() or str(chat_id or "").strip(),
                _hb_text,
                log_worker_id=agent_instance_label or None,
                log_username=(state.get("username") or "").strip() or None,
                log_plan_title=_hb_plan_log,
                outbound_bot_token=_out_hb_tok,
            )
            worker_invoke = worker_graph.invoke(worker_state, trace_cfg)
            raw_worker_reply = str(
                worker_invoke.get("internal_reply")
                or worker_invoke.get("reply")
                or worker_invoke.get("output")
                or "Sin respuesta."
            )
            reply = raw_worker_reply
            _label_reply = f"{assigned} {run_label_n}".strip()
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
            reply = _prepend_subagent_label_once(reply, _label_e)
            status = "FAILED"
        finally:
            _wdb = getattr(worker_graph, "_worker_db", None) if worker_graph is not None else None
            if _suspend_for_rw_worker and _wdb is not None and _wdb is not db:
                try:
                    _wdb.close()
                except Exception:
                    pass
                _worker_graph_cache.pop(worker_cache_key, None)
            if _suspend_for_rw_worker:
                try:
                    db.resume_readonly_file_handle()
                except Exception:
                    pass
            if slot_token:
                release_subagent_slot(tenant_id, assigned, slot_token, str(chat_id or ""))
            set_idle(chat_id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            append_task_audit(db, chat_id, assigned, incoming, status, elapsed_ms, plan_title=plan_title)

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
        photos: list[str] = []
        if isinstance(worker_invoke, dict):
            raw_pl = worker_invoke.get("sandbox_photos_base64")
            if isinstance(raw_pl, list):
                photos = [str(x).strip() for x in raw_pl if isinstance(x, str) and str(x).strip()]
        if not photos and messages is not None:
            photos = extract_latest_sandbox_figures_base64(messages)
        if not photos:
            b64 = ""
            if isinstance(worker_invoke, dict):
                b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
            if not b64 and messages is not None:
                b64 = extract_latest_sandbox_figure_base64(messages) or ""
            if b64:
                photos = [b64]
        if len(photos) == 1:
            out["sandbox_photo_base64"] = photos[0]
        elif len(photos) > 1:
            out["sandbox_photos_base64"] = photos
            out["sandbox_photo_base64"] = photos[0]
        doc_paths: list[str] = []
        if isinstance(worker_invoke, dict):
            raw_docs = worker_invoke.get("sandbox_document_paths")
            if isinstance(raw_docs, list):
                doc_paths = [str(x).strip() for x in raw_docs if isinstance(x, str) and str(x).strip()]
        if not doc_paths and messages is not None:
            doc_paths = extract_latest_sandbox_document_paths(messages)
        if doc_paths:
            out["sandbox_document_paths"] = doc_paths
        if "active_mission" in state:
            out["active_mission"] = state.get("active_mission")
        if "handoff_context" in state:
            out["handoff_context"] = state.get("handoff_context")
        out["last_worker_raw_reply"] = raw_worker_reply or reply
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
            "TAREA: Misión A2A INCOME_INJECTION. El usuario pide búsqueda de empleo y/o enlaces para postular.",
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
        synthetic = f"TAREA: Misión A2A JOB_OPPORTUNITY_TRACKING.\n{user_ctx}"
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
            synthesis_task = (
                "TAREA: JobHunter persistió datos en finance_worker.job_opportunities. "
                "Responde en 2–5 frases en español: confirmación, estado (tracking/applied) y siguiente paso concreto. "
                "No pegues bloques SQL crudos."
            )
        else:
            mission_system_message = (
                f"JobHunter ha completado la misión {mission_name}. "
                f"Aquí están los resultados crudos: {raw_job_hunter_reply}\n\n"
                "Sintetiza esto en tu reporte financiero final."
            )
            synthesis_task = (
                "TAREA: JobHunter completó la misión INCOME_INJECTION. "
                "Sintetiza los resultados crudos en un reporte financiero final para el usuario. "
                "No devuelvas el bloque crudo completo tal cual: prioriza 3 vacantes accionables, "
                "impacto esperado en flujo de caja y próximos pasos concretos."
            )

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
            "end": END,
        },
    )
    graph.add_edge("return_to_source", "invoke_worker")
    graph.add_edge("handoff_to_target", "invoke_worker")
    graph.add_edge("handoff_job_track", "invoke_worker")
    return graph.compile()
