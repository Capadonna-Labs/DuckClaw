from __future__ import annotations

import importlib
from types import SimpleNamespace


def _runtime_policy(*names: str):
    from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy

    capabilities = tuple(
        WorkerCapability(
            capability_id=f"cap_{name}",
            name=name,
            kind="runtime_policy",
            provider="duckclaw",
            permission="use",
            config={},
            policy={},
            quota={},
        )
        for name in names
    )
    return WorkerRuntimePolicy(
        worker_id="worker_alpha",
        identity=None,
        capabilities=capabilities,
    )


def _spec_with_capabilities(*names: str):
    return SimpleNamespace(runtime_policy=_runtime_policy(*names))


def test_finance_ledger_read_sql_depends_on_runtime_policy_and_available_tool() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("finance_ledger"),
        incoming="Resumen de mis cuentas bancarias",
        available_tools={"read_sql", "admin_sql"},
    )

    assert decision.tool_name == "read_sql"
    assert decision.reason == "finance_ledger.read_sql.local_accounts"
    assert not decision.requires_heuristic_first_tool

    missing_capability = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("market_data_bridge"),
        incoming="Resumen de mis cuentas bancarias",
        available_tools={"read_sql", "admin_sql"},
    )
    assert not missing_capability.should_force

    missing_tool = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("finance_ledger"),
        incoming="Resumen de mis cuentas bancarias",
        available_tools={"admin_sql"},
    )
    assert not missing_tool.should_force


def test_finance_ledger_admin_sql_write_decision_is_explicit() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("finance_ledger"),
        incoming="Actualiza el saldo de Efectivo a 46400 COP",
        available_tools={"read_sql", "admin_sql"},
    )

    assert decision.tool_name == "admin_sql"
    assert decision.reason == "finance_ledger.admin_sql.local_account_write"
    assert decision.requires_heuristic_first_tool


def test_finance_current_time_decision_is_direct_tool_call_once_per_turn() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities("finance_ledger"),
        incoming="Resumen de mis deudas",
        available_tools={"get_current_time", "read_sql"},
        called_tools_since_last_human=set(),
    )

    assert decision.tool_name == "get_current_time"
    assert decision.direct_tool_call
    assert decision.tool_args == {}
    assert decision.reason == "finance_ledger.current_time"

    already_called = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities("finance_ledger"),
        incoming="Resumen de mis deudas",
        available_tools={"get_current_time", "read_sql"},
        called_tools_since_last_human={"get_current_time"},
    )
    assert not already_called.should_force


def test_market_data_decision_uses_runtime_policy_message_and_blockers() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_market_data_tool_invocation(
        spec=_spec_with_capabilities("market_data_bridge"),
        incoming="Trae velas OHLCV de SPY",
        available_tools={"fetch_market_data"},
        blocked_by_prior_decision=False,
    )

    assert decision.tool_name == "fetch_market_data"
    assert decision.reason == "market_data_bridge.fetch_market_data.ohlcv"

    blocked = policy.decide_market_data_tool_invocation(
        spec=_spec_with_capabilities("market_data_bridge"),
        incoming="Trae velas OHLCV de SPY",
        available_tools={"fetch_market_data"},
        blocked_by_prior_decision=True,
    )
    assert not blocked.should_force


def test_ib_gateway_market_data_decision_uses_quant_runtime_policy() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_ib_gateway_market_data_tool_invocation(
        spec=_spec_with_capabilities("quant_trading"),
        incoming="Trae velas OHLCV de SPY",
        available_tools={"fetch_ib_gateway_ohlcv", "fetch_market_data"},
        ib_gateway_ohlcv_enabled=True,
    )

    assert decision.tool_name == "fetch_ib_gateway_ohlcv"
    assert decision.reason == "quant_trading.fetch_ib_gateway_ohlcv.ohlcv"

    disabled = policy.decide_ib_gateway_market_data_tool_invocation(
        spec=_spec_with_capabilities("quant_trading"),
        incoming="Trae velas OHLCV de SPY",
        available_tools={"fetch_ib_gateway_ohlcv", "fetch_market_data"},
        ib_gateway_ohlcv_enabled=False,
    )
    assert not disabled.should_force
