"""Runtime-policy decisions for forced worker tool invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Collection, Mapping

from duckclaw.finance.runtime_policy import (
    finanz_should_force_current_time,
    finanz_user_requests_ohlcv_ingest,
    is_finanz_budgets_query,
    is_finanz_debts_query,
    is_finanz_local_account_write_query,
    is_finanz_local_accounts_query,
    is_finanz_validate_db_intent,
)
from duckclaw.workers.runtime_policy_helpers import worker_has_runtime_capability


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
        or not worker_has_runtime_capability(spec, "finance_ledger")
    ):
        return _no_tool_invocation()

    if "admin_sql" in tool_names and is_finanz_local_account_write_query(incoming):
        return ToolInvocationDecision(
            tool_name="admin_sql",
            reason="finance_ledger.admin_sql.local_account_write",
        )

    if "read_sql" not in tool_names:
        return _no_tool_invocation()

    read_sql_reasons = (
        ("local_accounts", is_finanz_local_accounts_query),
        ("debts", is_finanz_debts_query),
        ("budgets", is_finanz_budgets_query),
        ("db_validation", is_finanz_validate_db_intent),
    )
    for reason_suffix, predicate in read_sql_reasons:
        if predicate(incoming):
            return ToolInvocationDecision(
                tool_name="read_sql",
                reason=f"finance_ledger.read_sql.{reason_suffix}",
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
        or not worker_has_runtime_capability(spec, "finance_ledger")
        or not finanz_should_force_current_time(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="get_current_time",
        reason="finance_ledger.current_time",
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
        or not worker_has_runtime_capability(spec, "market_data_bridge")
        or not finanz_user_requests_ohlcv_ingest(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="fetch_market_data",
        reason="market_data_bridge.fetch_market_data.ohlcv",
    )


def decide_ib_gateway_market_data_tool_invocation(
    *,
    spec: Any,
    incoming: str,
    available_tools: Collection[str] | Mapping[str, Any],
    ib_gateway_ohlcv_enabled: bool,
    already_has_tool_result: bool = False,
    summarize_ok_for_forced_ohlcv: bool = True,
    blocked_by_prior_decision: bool = False,
    heuristic_first_tool_enabled: bool = True,
) -> ToolInvocationDecision:
    """Choose the dedicated IB Gateway OHLCV tool for quant runtime policies."""

    tool_names = _tool_names(available_tools)
    if (
        already_has_tool_result
        or blocked_by_prior_decision
        or not heuristic_first_tool_enabled
        or not summarize_ok_for_forced_ohlcv
        or not ib_gateway_ohlcv_enabled
        or "fetch_ib_gateway_ohlcv" not in tool_names
        or not worker_has_runtime_capability(spec, "quant_trading")
        or not finanz_user_requests_ohlcv_ingest(incoming)
    ):
        return _no_tool_invocation()

    return ToolInvocationDecision(
        tool_name="fetch_ib_gateway_ohlcv",
        reason="quant_trading.fetch_ib_gateway_ohlcv.ohlcv",
    )

