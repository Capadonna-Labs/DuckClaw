"""Pure task-intent classification helpers for the manager graph."""

from __future__ import annotations

import re


def _incoming_has_context_summary_system_directive(incoming: str) -> bool:
    """Directivas del gateway (/context) con volcado largo no son misiones Job-Hunter."""
    text = incoming or ""
    return (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in text
        or "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in text
    )


def _incoming_looks_like_semantic_context_followup(incoming: str) -> bool:
    """
    Heuristica: el usuario pregunta por notas ya indexadas (VSS) sin pegar el cuerpo.
    Misma superficie de tools que SUMMARIZE_* (stdio MCP liviano / sin Reddit-GitHub).
    """
    raw = (incoming or "").strip()
    if not raw or _incoming_has_context_summary_system_directive(raw):
        return False
    text = raw.lower()
    if re.search(
        r"\b(qué|que|hay|algo)\s+.+\s+(en el contexto|en mi contexto|en la memoria)\b",
        text,
    ):
        return True
    if re.search(r"\b(en el contexto|en mi contexto|en la memoria)\s*\?", text):
        return True
    if re.search(
        r"\b(tenemos anotado|hay anotado|notas sobre|contexto indexado|memoria semántica|memoria semantica)\b",
        text,
    ):
        return True
    return "search_semantic" in text


def _worker_should_use_lite_stdio_mcp_surface(text: str) -> bool:
    return _incoming_has_context_summary_system_directive(text) or _incoming_looks_like_semantic_context_followup(
        text
    )


_NON_LABOR_OFERTA_RE = re.compile(
    r"shock\s+de\s+oferta|oferta\s+y\s+demanda|oferta\s+petrol|oferta\s+energ",
    re.IGNORECASE,
)
_LABOR_OFERTA_RE = re.compile(
    r"\boferta(s)?\s+(de\s+)?(empleo|trabajo|laboral)\b|\bofertas?\s+laborales?\b",
    re.IGNORECASE,
)


def _text_has_word_boundary(term: str, text: str) -> bool:
    if not term or not text:
        return False
    return bool(re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE))


def _job_labor_terms_in_text(text: str) -> bool:
    """Terminos de mercado laboral; "oferta" sola no cuenta."""
    if not text:
        return False
    single_word = (
        "trabajo",
        "empleo",
        "vacante",
        "vacantes",
        "linkedin",
        "greenhouse",
        "lever",
        "postular",
        "aplicar",
        "hiring",
        "headhunter",
    )
    if any(_text_has_word_boundary(word, text) for word in single_word):
        return True
    for phrase in ("data scientist", "científico de datos", "ciencia de datos"):
        if phrase in text:
            return True
    return bool(_LABOR_OFERTA_RE.search(text))


def _job_action_terms_in_text(text: str) -> bool:
    """Accion de busqueda laboral; evita "buscan" por substring de "busca"."""
    action_terms = (
        "busca",
        "busco",
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
    return any(_text_has_word_boundary(term, text) for term in action_terms) or "http" in text or "www." in text


def _looks_like_job_add_command(incoming: str) -> bool:
    raw = (incoming or "").strip().lower()
    if not raw:
        return False
    return (raw.startswith("/job --add ") or raw.startswith("/job add ")) and (
        "http://" in raw or "https://" in raw
    )


def _job_hunter_user_requests_application_tracking(incoming: str) -> bool:
    """
    Seguimiento de postulaciones ya guardadas (DuckDB), sin discovery Tavily.
    Ej.: "dame el seguimiento de las vacantes a las que he aplicado".
    """
    raw = (incoming or "").strip()
    if not raw:
        return False
    text_lower = raw.lower()
    if text_lower.startswith("tarea:"):
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
    if not any(keyword in text_lower for keyword in tracking_kw):
        return False
    job_kw = ("vacante", "vacantes", "empleo", "trabajo", "postul", "aplic", "oferta", "ofertas")
    return any(keyword in text_lower for keyword in job_kw)


def job_hunter_user_requests_job_search(incoming: str) -> bool:
    """
    True si el texto implica busqueda de empleo con accion concreta.
    Usado por el planner del manager y por el worker para forzar tavily_search en primer turno.
    """
    raw = (incoming or "").strip()
    if not raw:
        return False
    if _incoming_has_context_summary_system_directive(raw):
        return False
    text = raw.lower()
    if _looks_like_job_add_command(raw):
        return False
    if _job_hunter_user_requests_application_tracking(raw):
        return False
    if any(
        marker in text
        for marker in (
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
    if "tavily_search" in text:
        return True
    if "tarea:" in text and "tavily" in text:
        return True
    if text.startswith("tarea:") and any(
        marker in text
        for marker in (
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
    return _job_labor_terms_in_text(text) and _job_action_terms_in_text(text)


def _user_signals_cashflow_stress(incoming: str) -> bool:
    """Detecta estres de caja / iliquidez en espanol coloquial."""
    if _incoming_has_context_summary_system_directive(incoming or ""):
        return False
    text = (incoming or "").strip().lower()
    if not text:
        return False
    stress_terms = (
        "iliquido",
        "ilíquido",
        "sin plata",
        "sin dinero",
        "sin liquidez",
        "no me alcanza",
        "no me va a alcanzar",
        "necesito ingresos",
        "ingreso extra",
        "ingresos extra",
        "conseguir trabajo",
        "buscar trabajo",
        "buscar empleo",
        "conseguir empleo",
    )
    if any(term in text for term in stress_terms):
        return True
    if "flujo de caja" in text:
        return bool(
            re.search(
                r"\b(mi|mis|me|mí|no me alcanza|iliquid|ilíquid|sin (plata|dinero|liquidez))\b",
                text,
            )
        )
    return False


__all__ = [
    "_LABOR_OFERTA_RE",
    "_NON_LABOR_OFERTA_RE",
    "_incoming_has_context_summary_system_directive",
    "_incoming_looks_like_semantic_context_followup",
    "_job_action_terms_in_text",
    "_job_hunter_user_requests_application_tracking",
    "_job_labor_terms_in_text",
    "_looks_like_job_add_command",
    "_text_has_word_boundary",
    "_user_signals_cashflow_stress",
    "_worker_should_use_lite_stdio_mcp_surface",
    "job_hunter_user_requests_job_search",
]
