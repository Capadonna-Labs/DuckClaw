"""
Context-Guard: FactCheckerNode y SelfCorrectionNode para prevención de alucinaciones.

Spec: specs/RAG_Fact_Checker_Context_Guard.md

Próxima fase (retail, salida determinista):
    Añadir un paso de validación **después** del modelo (p. ej. en ``set_reply`` del
    WorkerFactory o un nodo ``output_validator``) que:
    - extraiga del texto final números telefónicos (regex CO/intl.) y handles de redes (@usuario);
    - los compare contra una allowlist derivada del bloque CONTACTO OFICIAL (soul/config);
    - si aparece un teléfono o @ no autorizado, sustituya la respuesta por escalado a la dueña
      o dispare handoff, sin depender solo del LLM del FactChecker.
    Workers retail sin ``catalog_retriever`` no activan Context-Guard; este chequeo
    sería complementario y aplicable aunque ``fact_check`` esté deshabilitado.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from duckclaw.guardrails.loader import load_guardrail

FACT_CHECKER_PROMPT = load_guardrail("validators", "fact_checker")
SELF_CORRECTION_PROMPT = load_guardrail("validators", "self_correction")


def extract_raw_evidence_from_messages(messages: list) -> Optional[str]:
    """
    Extrae el JSON de raw_evidence del último ToolMessage de catalog_retriever.
    Retorna None si no hay evidencia de catalog_retriever.
    """
    tool_call_ids_by_name: dict[str, str] = {}
    last_catalog_content: Optional[str] = None

    for i, msg in enumerate(messages):
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = (tc.get("name") or "").strip()
                tid = tc.get("id") or ""
                if name and tid:
                    tool_call_ids_by_name[tid] = name
        # ToolMessage: tiene tool_call_id y content
        if hasattr(msg, "tool_call_id") and hasattr(msg, "content"):
            tid = getattr(msg, "tool_call_id", "") or ""
            name = tool_call_ids_by_name.get(tid, "")
            if name == "catalog_retriever":
                content = getattr(msg, "content", None) or ""
                if content and isinstance(content, str):
                    last_catalog_content = content

    return last_catalog_content


def _parse_fact_check_result(response_text: str) -> tuple[bool, str]:
    """Parsea la respuesta del auditor. Retorna (is_safe, feedback)."""
    text = (response_text or "").strip()
    # Intentar extraer JSON del texto (el modelo puede rodear con markdown)
    json_match = re.search(r"\{[^{}]*\"is_safe\"[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            is_safe = bool(data.get("is_safe", False))
            feedback = (data.get("feedback") or "").strip() or "Sin razón especificada."
            return is_safe, feedback
        except json.JSONDecodeError:
            pass
    # Fallback: si no se puede parsear, asumir inseguro (fail-safe)
    return False, "Fallo en el parseo del auditor."


def fact_checker_node(
    state: dict[str, Any],
    llm: Any,
    *,
    raw_evidence: Optional[str] = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """
    Nodo FactChecker: valida draft_response contra raw_evidence.
    Retorna actualización de state con is_safe, correction_feedback, context_guard_route.
    """
    messages = state.get("messages") or []
    if llm is None:
        return {"messages": messages, "is_safe": True, "context_guard_route": "approved"}
    if not messages:
        return {"messages": messages, "is_safe": True, "context_guard_route": "approved"}

    last = messages[-1]
    draft_response = getattr(last, "content", None) or str(last)
    draft_response = (draft_response or "").strip()

    evidence = raw_evidence or extract_raw_evidence_from_messages(messages)
    if not evidence:
        return {"messages": messages, "is_safe": True, "context_guard_route": "approved"}

    correction_retries = int(state.get("correction_retries", 0))

    prompt = FACT_CHECKER_PROMPT.format(
        raw_evidence=evidence[:8000],
        draft_response=draft_response[:4000],
    )

    try:
        response = llm.invoke([SystemMessage(content=prompt)])
        content = getattr(response, "content", None) or str(response)
        is_safe, feedback = _parse_fact_check_result(content)
    except Exception as e:
        logging.getLogger(__name__).warning("FactCheckerNode falló: %s", e)
        is_safe = False
        feedback = f"Error en auditor: {e}"

    base = {"messages": messages}

    if is_safe:
        return {
            **base,
            "is_safe": True,
            "raw_evidence": evidence,
            "context_guard_route": "approved",
            "context_guard_approved_first_try": correction_retries == 0,
        }

    if correction_retries >= max_retries:
        return {
            **base,
            "is_safe": False,
            "raw_evidence": evidence,
            "correction_feedback": feedback,
            "context_guard_route": "handoff",
            "hallucination_prevented": True,  # Para LangSmith/SFT_DataCollector
        }

    return {
        **base,
        "is_safe": False,
        "raw_evidence": evidence,
        "correction_feedback": feedback,
        "context_guard_route": "correct",
        "hallucination_prevented": True,  # Para LangSmith/SFT_DataCollector
    }


def self_correction_node(
    state: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    """
    Nodo SelfCorrection: reescribe el draft usando correction_feedback y raw_evidence.
    Actualiza messages con el nuevo AIMessage y incrementa correction_retries.
    """
    if llm is None:
        return {
            "messages": state.get("messages", []),
            "correction_retries": int(state.get("correction_retries", 0)) + 1,
            "raw_evidence": state.get("raw_evidence"),
        }
    messages = list(state.get("messages") or [])
    correction_feedback = (state.get("correction_feedback") or "").strip()
    evidence = state.get("raw_evidence") or extract_raw_evidence_from_messages(messages)
    retries = int(state.get("correction_retries", 0))

    prompt = SELF_CORRECTION_PROMPT.format(
        correction_feedback=correction_feedback or "Información no respaldada por la evidencia.",
        raw_evidence=(evidence or "[]")[:8000],
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        new_content = getattr(response, "content", None) or str(response)
        new_content = (new_content or "").strip()
    except Exception as e:
        logging.getLogger(__name__).warning("SelfCorrectionNode falló: %s", e)
        new_content = "No pude reescribir la respuesta. Por favor, contacta a un especialista."

    # Reemplazar último AIMessage con la corrección
    new_msgs = messages[:-1] + [AIMessage(content=new_content)]

    return {
        "messages": new_msgs,
        "correction_retries": retries + 1,
        "raw_evidence": evidence,
    }


def handoff_reply_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Nodo HandoffReply: cuando FactChecker alcanza max retries, dispara handoff y retorna mensaje.
    """
    context_summary = (state.get("correction_feedback") or "Alucinación detectada tras múltiples intentos.")[:500]
    try:
        from duckclaw.activity.handoff_context import get_handoff_thread_id
        from duckclaw.activity.session_state import SessionStateManager
        thread_id = get_handoff_thread_id()
        mgr = SessionStateManager()
        mgr.request_handoff(thread_id, "context_guard_max_retries", context_summary)
    except Exception:
        pass
    return {"reply": "He notificado a un especialista. Te contactarán en breve."}
