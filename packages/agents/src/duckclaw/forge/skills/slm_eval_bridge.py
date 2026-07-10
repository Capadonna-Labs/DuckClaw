"""Skill bridge: execute_slm (teacher-student eval vía MLX-Inference)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from duckclaw.slm import ExecuteSLMRequest, execute_slm_http, validate_slm_xml_output
from duckclaw.slm.session import is_slm_enabled_for_chat, resolve_slm_session_for_chat
from duckclaw.workers.field_reflection import lesson_belief_key, persist_field_lesson

_log = logging.getLogger(__name__)


def _worker_schema(db: Any) -> str:
    if db is None:
        return "main"
    schema = getattr(db, "schema", None) or getattr(db, "default_schema", None)
    return str(schema or "main").strip() or "main"


def _execute_slm_impl(
    prompt: str,
    adapter_path: str = "default",
    temperature: float = 0.0,
    max_tokens: int = 256,
    chat_id: str = "",
    *,
    db: Any = None,
) -> str:
    cid = (chat_id or "").strip()
    if cid and db is not None and not is_slm_enabled_for_chat(db, cid):
        return (
            "SLM no habilitado para esta conversación. "
            "Activa SLM (opcional) en la consola admin antes de evaluar."
        )
    session = (
        resolve_slm_session_for_chat(db, cid)
        if cid
        else resolve_slm_session_for_chat(None, "")
    )
    req = ExecuteSLMRequest(
        prompt=prompt,
        adapter_path=adapter_path,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return execute_slm_http(
        req,
        base_url=session.get("base_url", ""),
        model=session.get("model", ""),
    )


def _record_slm_eval_lesson_impl(
    context_trigger: str,
    lesson_text: str,
    confidence_score: float = 0.85,
    chat_id: str = "",
    *,
    db: Any = None,
) -> str:
    if db is None:
        return json.dumps({"ok": False, "error": "DB no disponible para field_lesson"})
    trigger = (context_trigger or "").strip() or f"slm_eval:{chat_id or 'session'}"
    lesson = (lesson_text or "").strip()
    if not lesson:
        return json.dumps({"ok": False, "error": "lesson_text vacío"})
    schema = _worker_schema(db)
    key = lesson_belief_key(trigger, lesson)
    persist_field_lesson(
        db,
        schema,
        key,
        trigger,
        lesson,
        float(confidence_score),
    )
    return json.dumps(
        {
            "ok": True,
            "belief_key": key,
            "context_trigger": trigger,
            "message": "Lección RSI persistida en agent_beliefs (field_lesson).",
        },
        ensure_ascii=False,
    )


def _request_model_approval_impl(
    adapter_path: str,
    summary: str = "",
    chat_id: str = "",
) -> str:
    from duckclaw.hitl.model_approval_service import request_model_approval

    return request_model_approval(
        adapter_path=adapter_path,
        summary=summary,
        chat_id=chat_id,
    )


def register_slm_eval_skill(
    tools_list: list[Any],
    slm_eval_config: Optional[dict] = None,
    *,
    db: Any = None,
) -> None:
    cfg = slm_eval_config if isinstance(slm_eval_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return

    def _execute_slm(
        prompt: str,
        adapter_path: str = "default",
        temperature: float = 0.0,
        max_tokens: int = 256,
        chat_id: str = "",
    ) -> str:
        return _execute_slm_impl(
            prompt,
            adapter_path=adapter_path,
            temperature=temperature,
            max_tokens=max_tokens,
            chat_id=chat_id,
            db=db,
        )

    def _record_lesson(
        context_trigger: str,
        lesson_text: str,
        confidence_score: float = 0.85,
        chat_id: str = "",
    ) -> str:
        return _record_slm_eval_lesson_impl(
            context_trigger,
            lesson_text,
            confidence_score=confidence_score,
            chat_id=chat_id,
            db=db,
        )

    def _request_approval(adapter_path: str, summary: str = "", chat_id: str = "") -> str:
        return _request_model_approval_impl(adapter_path, summary=summary, chat_id=chat_id)

    tools_list.append(
        StructuredTool.from_function(
            _execute_slm,
            name="execute_slm",
            description=(
                "Inyecta un prompt sintético en el SLM local (MLX-Inference PM2) "
                "para evaluar formato XML, tool_calls y adherencia. "
                "Usar temperature=0 para eval determinística. "
                "Requiere SLM habilitado en la conversación."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _record_lesson,
            name="record_slm_eval_lesson",
            description=(
                "Persiste una lección RSI (field_lesson) cuando el SLM falla el examen. "
                "Parámetros: context_trigger, lesson_text, confidence_score."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _request_approval,
            name="request_model_approval",
            description=(
                "Solicita aprobación HITL para promover un adapter LoRA a producción. "
                "El admin debe confirmar con /approve-model."
            ),
        )
    )
    _ = validate_slm_xml_output  # referenced in tests/docs
