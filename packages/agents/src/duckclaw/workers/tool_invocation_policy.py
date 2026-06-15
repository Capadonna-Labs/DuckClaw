"""Runtime-policy decisions for forced worker tool invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Collection, Mapping

from duckclaw.workers.runtime_policy_helpers import worker_has_runtime_capability

LOCAL_LEDGER_CAPABILITY = "local_ledger"
MARKET_DATA_CAPABILITY = "market_data_bridge"
BROKER_MARKET_DATA_CAPABILITY = "broker_market_data"


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


def _has_broker_market_data_capability(spec: Any) -> bool:
    return _has_any_capability(spec, BROKER_MARKET_DATA_CAPABILITY)


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


def _local_record_write_intent(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    if not re.search(
        r"\b(actualiza|actualizar|cambia|cambiar|modifica|modificar|ajusta|ajustar|"
        r"pone|poner|ponga|pon\b|establece|establecer|fija|fijar|deja|dejar|"
        r"corrige|corregir|setea|setear)\b",
        value,
    ):
        return False
    return bool(
        "saldo" in value
        or "balance" in value
        or ("cuenta" in value and re.search(r"\b(cop|pesos?|cero|0|\d[\d.,]*)\b", value))
    )


def _local_records_query(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    return bool(
        re.search(
            r"\b(resumen\s+(de\s+)?(mis\s+)?cuentas|saldos?\s+(de\s+)?(mis\s+)?cuentas|"
            r"cuentas\s+bancarias|estado\s+actual\s+de\s+mis\s+cuentas|"
            r"estatus\s+de\s+mis\s+cuentas)\b",
            value,
        )
    )


def _obligations_query(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    return bool(
        re.search(
            r"\b(resumen\s+(de\s+)?(mis\s+)?deudas|mis\s+deudas|"
            r"deudas\s+(activas|pendientes|registradas)|cu[aá]nto\s+debo\b|"
            r"cu[aá]ntas\s+deudas|estado\s+(de\s+)?(mis\s+)?deudas|"
            r"listado\s+(de\s+)?(mis\s+)?deudas|qu[eé]\s+deudas\s+tengo|"
            r"total\s+(de\s+)?(mis\s+)?deudas|deudas\s+en\s+(la\s+)?(base|db|duckdb))\b",
            value,
        )
    )


def _budget_query(text: str) -> bool:
    value = (text or "").strip().lower()
    if _looks_like_system_or_non_data_turn(value):
        return False
    return bool(
        re.search(
            r"\b(resumen\s+(de\s+)?(mis\s+)?presupuestos?|mis\s+presupuestos?|"
            r"presupuestos?\s+(del\s+)?mes|estado\s+(de\s+)?(mis\s+)?presupuestos?|"
            r"listado\s+(de\s+)?(mis\s+)?presupuestos?|presupuesto\s+vs\s+real|"
            r"cu[aá]nto\s+llevo\s+(gastad[oa]\s+)?(de\s+)?(mis\s+)?presupuestos?|"
            r"presupuestos?\s+en\s+(la\s+)?(base|db|duckdb))\b",
            value,
        )
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
    if _obligations_query(value) or _local_records_query(value) or _budget_query(value):
        return True
    return bool(
        re.search(
            r"\b(pasar\s+(la\s+)?deuda|mover\s+(la\s+)?(deuda|cuota)|"
            r"vencimient|cuota\s+(de|del))\b",
            value,
        )
    )


def _market_data_ingest_intent(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if low.startswith("[meta:"):
        return False
    if "ohlcv" in low and any(
        marker in low for marker in ("trae", "descarga", "importa", "ingesta", "actualiza", "bajar", "pull")
    ):
        return True
    if not any(marker in low for marker in ("vela", "ohlcv", "candle", "fetch_market", "fetch market")):
        return False
    return bool(re.search(r"\b[A-Z]{1,5}\b", raw))


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
        ("local_records", _local_records_query),
        ("obligations", _obligations_query),
        ("budgets", _budget_query),
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
    if (
        already_has_tool_result
        or summarize_directive
        or orchestration_active
        or "get_current_time" not in tool_names
        or "get_current_time" in set(called_tools_since_last_human)
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


def decide_market_data_tool_invocation(
    *,
    spec: Any,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    already_has_tool_result: bool = False,
    summarize_ok_for_forced_ohlcv: bool = True,
    blocked_by_prior_decision: bool = False,
    heuristic_first_tool_enabled: bool = True,
) -> ToolInvocationDecision:
    """Choose market-data forcing from runtime policy and explicit OHLCV intent."""

    tool_names = _tool_names(available_tools)
    if (
        already_has_tool_result
        or blocked_by_prior_decision
        or not heuristic_first_tool_enabled
        or not summarize_ok_for_forced_ohlcv
        or "fetch_market_data" not in tool_names
        or not worker_has_runtime_capability(spec, MARKET_DATA_CAPABILITY)
        or not _market_data_ingest_intent(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="fetch_market_data",
        reason=f"{MARKET_DATA_CAPABILITY}.fetch_market_data.ohlcv",
    )


def decide_broker_market_data_tool_invocation(
    *,
    spec: Any,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    broker_market_data_enabled: bool,
    broker_tool_name: str = "fetch_broker_ohlcv",
    already_has_tool_result: bool = False,
    summarize_ok_for_forced_ohlcv: bool = True,
    blocked_by_prior_decision: bool = False,
    heuristic_first_tool_enabled: bool = True,
) -> ToolInvocationDecision:
    """Choose a dedicated broker OHLCV tool from runtime policy."""

    tool_names = _tool_names(available_tools)
    if (
        already_has_tool_result
        or blocked_by_prior_decision
        or not heuristic_first_tool_enabled
        or not summarize_ok_for_forced_ohlcv
        or not broker_market_data_enabled
        or broker_tool_name not in tool_names
        or not _has_broker_market_data_capability(spec)
        or not _market_data_ingest_intent(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name=broker_tool_name,
        reason=f"{BROKER_MARKET_DATA_CAPABILITY}.{broker_tool_name}.ohlcv",
    )
