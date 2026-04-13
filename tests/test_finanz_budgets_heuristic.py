"""Heurística finanz: presupuestos obligan read_sql (evita cifras inventadas sin DuckDB)."""

from duckclaw.workers.factory import _is_finanz_budgets_query, _is_finanz_debts_query


def test_is_finanz_budgets_query_resumen_mis_presupuestos() -> None:
    assert _is_finanz_budgets_query("Dame un resumen de mis presupuestos")
    assert _is_finanz_budgets_query("resumen de presupuestos")


def test_is_finanz_budgets_query_vs_real() -> None:
    assert _is_finanz_budgets_query("presupuesto vs real abril")
    assert _is_finanz_budgets_query("presupuestos vs real")


def test_is_finanz_budgets_query_negative() -> None:
    assert not _is_finanz_budgets_query("")
    assert not _is_finanz_budgets_query("compra acciones AAPL")
    assert not _is_finanz_budgets_query("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nfoo")


def test_is_finanz_debts_still_distinct_from_budgets() -> None:
    assert _is_finanz_debts_query("Dame un resumen de mis deudas")
    assert not _is_finanz_budgets_query("Dame un resumen de mis deudas")
    assert not _is_finanz_debts_query("Dame un resumen de mis presupuestos")
