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


def _current_time_anchor_intent(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    if _local_data_query(value):
        return True
    return bool(
        re.search(
            r"\b(fecha|hoy|ma[nñ]ana|vencimient|caduc|plazo|deadline|calendario|"
            r"esta\s+semana|este\s+mes|pr[oó]ximo\s+mes)\b",
            value,
        )
    )


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
    """Choose deterministic current-time anchoring from runtime policy."""

    tool_names = _tool_names(available_tools)
    gct_called = "get_current_time" in set(called_tools_since_last_human)
    if (
        already_has_tool_result
        or summarize_directive
        or (orchestration_active and gct_called)
        or "get_current_time" not in tool_names
        or gct_called
        or not _has_local_ledger_capability(spec)
        or not _current_time_anchor_intent(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="get_current_time",
        reason=f"{LOCAL_LEDGER_CAPABILITY}.current_time",
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
