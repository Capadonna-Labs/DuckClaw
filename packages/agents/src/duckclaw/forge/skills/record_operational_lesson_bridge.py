"""Skill bridge: record_operational_lesson → field_lesson en agent_beliefs."""

from __future__ import annotations

import json
from typing import Any, Optional

from duckclaw.workers.field_reflection import lesson_belief_key, persist_field_lesson


def _worker_schema(db: Any) -> str:
    if db is None:
        return "main"
    schema = getattr(db, "schema", None) or getattr(db, "default_schema", None)
    return str(schema or "main").strip() or "main"


def _record_operational_lesson_impl(
    lesson_text: str,
    context_trigger: str = "",
    lesson_type: str = "",
    confidence_score: float = 0.9,
    *,
    db: Any = None,
) -> str:
    if db is None:
        return json.dumps({"ok": False, "error": "DB no disponible para field_lesson"})
    lesson = (lesson_text or "").strip()
    if not lesson:
        return json.dumps({"ok": False, "error": "lesson_text vacío"})
    ltype = (lesson_type or "").strip()
    trigger = (context_trigger or "").strip()
    if ltype and trigger and ltype not in trigger:
        trigger = f"{ltype}:{trigger}"
    elif ltype and not trigger:
        trigger = ltype
    elif not trigger:
        trigger = "operational_lesson"
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
            "lesson_type": ltype or None,
            "context_trigger": trigger,
            "message": "Lección operativa persistida en agent_beliefs (field_lesson).",
        },
        ensure_ascii=False,
    )


def register_record_operational_lesson_skill(
    tools_list: list[Any],
    record_operational_lesson_config: Optional[dict] = None,
    *,
    db: Any = None,
) -> None:
    cfg = record_operational_lesson_config if isinstance(record_operational_lesson_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return

    def _record(
        lesson_text: str,
        context_trigger: str = "",
        lesson_type: str = "",
        confidence_score: float = 0.9,
    ) -> str:
        return _record_operational_lesson_impl(
            lesson_text,
            context_trigger=context_trigger,
            lesson_type=lesson_type,
            confidence_score=confidence_score,
            db=db,
        )

    tools_list.append(
        StructuredTool.from_function(
            _record,
            name="record_operational_lesson",
            description=(
                "Persiste una lección operativa (field_lesson) en agent_beliefs. "
                "Usar tras errores reales (p. ej. lesson_type=broker_position_hallucination). "
                "Parámetros: lesson_text, context_trigger, lesson_type, confidence_score."
            ),
        )
    )
