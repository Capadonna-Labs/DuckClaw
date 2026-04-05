"""Heurística finanz: resumen de cuentas locales + follow-up IBKR."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.workers.factory import (
    _finanz_should_force_ibkr_after_local_cuentas_read,
    _is_finanz_local_accounts_query,
)


def test_local_accounts_query_resumen_mis_cuentas() -> None:
    assert _is_finanz_local_accounts_query("Dame un resumen de mis cuentas")


def test_local_accounts_query_saldos() -> None:
    assert _is_finanz_local_accounts_query("saldos de mis cuentas")


def test_local_accounts_query_excludes_ibkr() -> None:
    assert not _is_finanz_local_accounts_query("resumen de mis cuentas en IBKR")


def test_local_accounts_query_excludes_portfolio_bolsa() -> None:
    assert not _is_finanz_local_accounts_query("resumen de mis cuentas y acciones en bolsa")


def test_force_ibkr_after_read_sql_true() -> None:
    msgs = [
        HumanMessage(content="Dame un resumen de mis cuentas"),
        AIMessage(content="", tool_calls=[{"name": "read_sql", "id": "1", "args": {}}]),
        ToolMessage(content='[{"name":"x"}]', tool_call_id="1", name="read_sql"),
    ]
    assert _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="finanz",
        has_ibkr=True,
    )


def test_force_ibkr_false_without_read_sql_last() -> None:
    msgs = [HumanMessage(content="Dame un resumen de mis cuentas")]
    assert not _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="finanz",
        has_ibkr=True,
    )


def test_force_ibkr_false_after_get_ibkr_already() -> None:
    """Último mensaje es read_sql pero ya hubo get_ibkr_portfolio tras el humano → no forzar de nuevo."""
    msgs = [
        HumanMessage(content="Dame un resumen de mis cuentas"),
        ToolMessage(content="[]", tool_call_id="a", name="read_sql"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(content="{}", tool_call_id="b", name="get_ibkr_portfolio"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(content="[]", tool_call_id="c", name="read_sql"),
    ]
    assert not _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="finanz",
        has_ibkr=True,
    )


def test_force_ibkr_false_wrong_worker() -> None:
    msgs = [
        HumanMessage(content="Dame un resumen de mis cuentas"),
        ToolMessage(content="[]", tool_call_id="1", name="read_sql"),
    ]
    assert not _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="other",
        has_ibkr=True,
    )


def test_force_ibkr_false_no_ibkr_skill() -> None:
    msgs = [
        HumanMessage(content="Dame un resumen de mis cuentas"),
        ToolMessage(content="[]", tool_call_id="1", name="read_sql"),
    ]
    assert not _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="finanz",
        has_ibkr=False,
    )


def test_force_ibkr_false_system_directive_in_human() -> None:
    msgs = [
        HumanMessage(content="[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT] algo"),
        ToolMessage(content="[]", tool_call_id="1", name="read_sql"),
    ]
    assert not _finanz_should_force_ibkr_after_local_cuentas_read(
        msgs,
        logical_worker_id="finanz",
        has_ibkr=True,
    )
