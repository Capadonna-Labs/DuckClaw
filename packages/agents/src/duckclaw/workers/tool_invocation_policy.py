"""Runtime-policy decisions for forced worker tool invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Collection, Mapping

from duckclaw.workers.runtime_policy_helpers import worker_has_runtime_capability

LOCAL_LEDGER_CAPABILITY = "local_ledger"


@dataclass(frozen=True)
class ToolInvocationDecision:
    """Decision object for asking the LLM or graph to invoke one tool first."""

    tool_name: str | None = None
    reason: str = ""
    direct_tool_call: bool = False
    tool_args: Mapping[str, Any] = field(default_factory=dict)
    requires_heuristic_first_tool: bool = True

    @property
    def should_force(self) -> bool:
        return bool(self.tool_name)

    def is_tool(self, tool_name: str) -> bool:
        return self.tool_name == tool_name


def _tool_names(available_tools: Collection[str] | Mapping[str, Any]) -> set[str]:
    if isinstance(available_tools, Mapping):
        return {str(name) for name in available_tools.keys()}
    return {str(name) for name in available_tools}


def _no_tool_invocation() -> ToolInvocationDecision:
    return ToolInvocationDecision()


def _has_any_capability(spec: Any, *capability_names: str) -> bool:
    return any(worker_has_runtime_capability(spec, name) for name in capability_names)


def _has_local_ledger_capability(spec: Any) -> bool:
    return _has_any_capability(spec, LOCAL_LEDGER_CAPABILITY)


def _looks_like_system_or_non_data_turn(text: str) -> bool:
    value = (text or "").strip().lower()
    if not value:
        return True
    if "[system_directive:" in value or value.startswith("[system_event:"):
        return True
    if re.match(r"^(gracias|muchas\s+gracias|ok\.?|vale\.?|listo\.?|perfecto\.?|entendido\.?)\s*!?$", value):
        return True
    if re.search(r"\b(ejecuta|corre|run|script|c[oó]digo|python|bash|programa|sandbox)\b", value):
        return True
    if "[vlm_context" in value or "contexto visual adjunto:" in value:
        return True
    if "[email_screenshot]" in value or "[directiva_correo]" in value:
        return True
    if re.search(r"https?://", value) or "reddit.com" in value:
        return True
    return False


def _mentions_local_db(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "duckdb",
            "base de datos",
            "en la base",
            "en la db",
            "en el hub",
            "tabla local",
            "datos locales",
            "registros locales",
        )
    )


def _local_record_write_intent(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    if not re.search(
        r"\b(actualiza|actualizar|cambia|cambiar|modifica|modificar|ajusta|ajustar|"
        r"inserta|insertar|borra|borrar|elimina|eliminar|"
        r"pone|poner|ponga|pon\b|establece|establecer|fija|fijar|deja|dejar|"
        r"corrige|corregir|setea|setear|persiste|persistir|guarda|guardar)\b",
        value,
    ):
        return False
    return bool(
        _mentions_local_db(value)
        or re.search(r"\b(registro|fila|tabla|columna|valor|campo|sql)\b", value)
    )


def _local_data_query(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    if re.search(r"\b(read_sql|inspect_schema)\b", value):
        return True
    read_verbs = re.search(
        r"\b(consulta|muestra|lista|resume|resumen|estado|detalle|cu[aá]nto|total)\b",
        value,
    )
    if not read_verbs:
        return False
    return bool(
        _mentions_local_db(value)
        or re.search(r"\b(registros?|datos|filas?|tablas?|persistid[oa]s?|schema)\b", value)
    )


def _db_validation_intent(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    if any(
        phrase in value
        for phrase in (
            "no estás usando tools",
            "no usas tools",
            "no usa tools",
            "sin herramientas",
            "sin tools",
            "usa read_sql",
            "usar read_sql",
            "usa las herramientas",
            "debes usar tools",
        )
    ):
        return True
    if re.search(r"\b(valida|verifica|comprueba|confirma)\b", value) and any(
        marker in value for marker in ("db", "duckdb", "base de datos", "en la base", "valores en")
    ):
        return True
    return "consulta" in value and any(marker in value for marker in ("duckdb", "base de datos", "en la db"))


def decide_db_first_tool_invocation(
    *,
    spec: Any,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    already_has_tool_result: bool = False,
    summarize_directive: bool = False,
    orchestration_active: bool = False,
) -> ToolInvocationDecision:
    """Choose read/admin SQL forcing from DB-backed runtime capabilities."""

    tool_names = _tool_names(available_tools)
    if (
        already_has_tool_result
        or summarize_directive
        or orchestration_active
        or not _has_local_ledger_capability(spec)
    ):
        return _no_tool_invocation()

    # Gmail/email turns must not burn the first hop on read_sql.
    try:
        from duckclaw.workers.tool_orchestration import incoming_has_email_intent

        if incoming_has_email_intent(incoming):
            return _no_tool_invocation()
    except Exception:
        pass

    if "admin_sql" in tool_names and _local_record_write_intent(incoming):
        return ToolInvocationDecision(
            tool_name="admin_sql",
            reason=f"{LOCAL_LEDGER_CAPABILITY}.admin_sql.local_record_write",
        )

    if "read_sql" not in tool_names:
        return _no_tool_invocation()

    read_sql_reasons = (
        ("local_data", _local_data_query),
        ("db_validation", _db_validation_intent),
    )
    for reason_suffix, predicate in read_sql_reasons:
        if predicate(incoming):
            return ToolInvocationDecision(
                tool_name="read_sql",
                reason=f"{LOCAL_LEDGER_CAPABILITY}.read_sql.{reason_suffix}",
                requires_heuristic_first_tool=False,
            )

    return _no_tool_invocation()


def decide_current_time_tool_invocation(
    *,
    spec: Any,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    called_tools_since_last_human: Collection[str],
    already_has_tool_result: bool = False,
    summarize_directive: bool = False,
    orchestration_active: bool = False,
) -> ToolInvocationDecision:
    """Force ``get_current_time`` once per user turn when the tool is bound.

    Time-sensitive replies need a real clock before session/hours claims. Skip
    only empty turns, system directives/events, summarize hops, and when the
    tool already ran this turn. ``spec`` retained for call-site compatibility.
    """
    _ = spec
    tool_names = _tool_names(available_tools)
    gct_called = "get_current_time" in set(called_tools_since_last_human)
    text = (incoming or "").strip()
    text_l = text.lower()
    if (
        already_has_tool_result
        or summarize_directive
        or (orchestration_active and gct_called)
        or "get_current_time" not in tool_names
        or gct_called
        or not text
        or "[system_directive:" in text_l
        or text_l.startswith("[system_event:")
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="get_current_time",
        reason="clock_anchor.get_current_time",
        direct_tool_call=True,
        tool_args={},
    )


def _update_system_prompt_intent(text: str) -> bool:
    """User asks to persist/adjust behavior into the worker system prompt (not DB rows)."""
    value = (text or "").strip().lower()
    if not value:
        return False
    if "[system_directive:" in value or value.startswith("[system_event:"):
        return False
    if "update_system_prompt" in value or "update_my_system_prompt" in value:
        return True
    # Frases cortas: «ajusta/actualiza/mejora/modifica tu prompt»
    if re.search(
        r"\b(ajusta|ajustar|actualiza|actualizar|mejora|mejorar|modifica|modificar|"
        r"cambia|cambiar|guarda|guardar|gu[aá]rdalo|gu[aá]rdala|a[nñ]ade|a[nñ]adir|"
        r"agrega|agregar|persiste|persistir|reescribe|reescribir|update|improve|adjust|"
        r"rewrite|append)\w*"
        r"\s+(?:un\s+poco\s+)?"
        r"(?:el\s+|la\s+|tu\s+|tus\s+|mi\s+|mis\s+|the\s+|your\s+|my\s+)?"
        r"(?:system\s+)?prompt\b"
        r"|\b(system\s+)?prompt\s+(?:del\s+sistema\s+)?"
        r"(?:aj[uú]stalo|actual[ií]zalo|mej[oó]ralo|modif[ií]calo|gu[aá]rdalo)\b",
        value,
    ):
        return True
    prompt_ref = re.search(
        r"\b(tu\s+|tus\s+|mi\s+|el\s+|la\s+|your\s+|my\s+|the\s+)?"
        r"(system\s+)?prompt\b"
        r"|\bprompt\s+del\s+sistema\b"
        r"|\binstrucciones\s+(del\s+sistema|permanentes|base)\b"
        r"|\bsystem\s+prompt\b",
        value,
    )
    if not prompt_ref:
        return False
    return bool(
        re.search(
            r"\b(ajusta|ajustar|actualiza|actualizar|mejora|mejorar|"
            r"guarda|guardar|gu[aá]rdalo|gu[aá]rdala|"
            r"a[nñ]ade|a[nñ]adir|agrega|agregar|persiste|persistir|"
            r"modifica|modificar|cambia|cambiar|escribe|escribir|"
            r"reescribe|reescribir|mete|incluir|incluye|"
            r"save|update|append|rewrite|improve|adjust|"
            r"pon(?:lo|la)?\s+en)\b",
            value,
        )
    )


def _is_loop_or_proactive_system_event(text: str) -> bool:
    """True for /loop or proactive-review SYSTEM_EVENT ticks (not ordinary chat)."""
    raw = (text or "").strip()
    if not raw.lower().startswith("[system_event:"):
        return False
    try:
        from duckclaw.graphs.proactive_review_markers import (
            proactive_review_event_phrase_in_text,
        )

        return proactive_review_event_phrase_in_text(raw)
    except Exception:
        return (
            "Ciclo de auto-mejora" in raw
            or "/loop" in raw
            or "Revisión periódica de /crons" in raw
            or "Revisión periódica de /goals" in raw
        )


def decide_loop_homeostasis_tool_invocation(
    *,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    called_tools_since_last_human: Collection[str] = (),
    already_has_tool_result: bool = False,
    summarize_directive: bool = False,
    homeostasis_streak: int = 0,
) -> ToolInvocationDecision:
    """
    Force ``evaluate_homeostasis`` as the first tool on /loop SYSTEM_EVENT ticks.

    Prompt text alone is not enough: db-first / orchestration often steal hop 1
    with ``read_sql``, and the agent then reports false "0 desviaciones" from
    ``assess_crons_alignment`` alone (missing SL breach / OCA / OHLCV sensors).

    When ``homeostasis_streak`` already hit the stuck limit, do **not** force
    another identical sensor call — the tools node injects nudge/escalate instead.
    """
    tool_names = _tool_names(available_tools)
    called = {str(n) for n in called_tools_since_last_human}
    if already_has_tool_result or summarize_directive:
        return _no_tool_invocation()
    if "evaluate_homeostasis" in called:
        return _no_tool_invocation()
    if "evaluate_homeostasis" not in tool_names:
        return _no_tool_invocation()
    if not _is_loop_or_proactive_system_event(incoming):
        return _no_tool_invocation()
    try:
        from duckclaw.workers.homeostasis_stuck import homeostasis_stuck_streak_limit

        if int(homeostasis_streak or 0) >= homeostasis_stuck_streak_limit():
            return _no_tool_invocation()
    except Exception:
        pass
    return ToolInvocationDecision(
        tool_name="evaluate_homeostasis",
        reason="platform.loop.evaluate_homeostasis.first_hop",
        requires_heuristic_first_tool=False,
    )


def decide_update_system_prompt_invocation(
    *,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    called_tools_since_last_human: Collection[str] = (),
    already_has_tool_result: bool = False,
    summarize_directive: bool = False,
) -> ToolInvocationDecision:
    """
    Force ``update_system_prompt`` when the user asks to persist prompt changes.

    Without tool_choice, models often invent a JSON block in chat instead of calling the tool
    (logs show ``tools usadas=ninguna`` while the reply claims success).
    """
    tool_names = _tool_names(available_tools)
    called = {str(n) for n in called_tools_since_last_human}
    if already_has_tool_result or summarize_directive:
        return _no_tool_invocation()
    if "update_system_prompt" in called or "update_my_system_prompt" in called:
        return _no_tool_invocation()
    if not _update_system_prompt_intent(incoming):
        return _no_tool_invocation()
    if "update_system_prompt" in tool_names:
        return ToolInvocationDecision(
            tool_name="update_system_prompt",
            reason="platform.update_system_prompt.persist_request",
            requires_heuristic_first_tool=False,
        )
    if "update_my_system_prompt" in tool_names:
        return ToolInvocationDecision(
            tool_name="update_my_system_prompt",
            reason="platform.update_my_system_prompt.persist_request",
            requires_heuristic_first_tool=False,
        )
    return _no_tool_invocation()
