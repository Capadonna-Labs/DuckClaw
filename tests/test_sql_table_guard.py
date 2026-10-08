"""Manifest allowed_tables: every referenced table must be allowed (no substring pass)."""

from __future__ import annotations

import json

import pytest

from duckclaw.workers.sql_table_guard import allowed_tables_error, referenced_tables

ALLOWED = ["demo_core.ohlcv_data", "demo_core.backtest_results", "finance_worker.trade_signals"]
SCHEMA = "finance_worker"


def _err(sql: str):
    return allowed_tables_error(ALLOWED, SCHEMA, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM demo_core.ohlcv_data WHERE ticker = 'MU'",
        "SELECT a.ticker FROM demo_core.ohlcv_data a JOIN demo_core.backtest_results b ON a.ticker = b.ticker",
        "INSERT INTO demo_core.backtest_results (strategy_name) VALUES ('x')",
        "WITH w AS (SELECT * FROM demo_core.ohlcv_data) SELECT * FROM w",
        "SELECT EXTRACT(YEAR FROM ts) FROM demo_core.ohlcv_data",
        "SELECT * FROM trade_signals",  # bare name in the worker's own schema
        "SELECT table_name FROM information_schema.tables",
        "SELECT * FROM duckdb_tables()",
        "SELECT * FROM read_csv('x.csv')",
        "SELECT 1",
        "SELECT * FROM demo_core.ohlcv_data WHERE note = 'FROM secrets'",  # literal ignored
        "INSERT INTO demo_core.backtest_results VALUES (1) ON CONFLICT DO UPDATE SET n = 1",
    ],
)
def test_allowed_statements_pass(sql: str) -> None:
    assert _err(sql) is None, referenced_tables(sql)


@pytest.mark.parametrize(
    "sql,bad",
    [
        # The old substring check let these through because an allowed name appeared.
        ("CREATE TABLE demo_core.montecarlo_results AS SELECT * FROM demo_core.ohlcv_data", "demo_core.montecarlo_results"),
        ("SELECT * FROM demo_core.ohlcv_data, demo_core.secret_keys", "demo_core.secret_keys"),
        ("SELECT * FROM demo_core.ohlcv_data o JOIN main.admin_console_users u ON 1=1", "main.admin_console_users"),
        ("DELETE FROM demo_core.fills USING demo_core.ohlcv_data", "demo_core.fills"),
        ("COPY demo_core.hrp_mandates TO 'out.csv'", "demo_core.hrp_mandates"),
        # Mentioning information_schema (even in a comment) used to disable the check.
        ("SELECT * FROM main.admin_console_users -- information_schema", "main.admin_console_users"),
    ],
)
def test_unlisted_tables_are_rejected(sql: str, bad: str) -> None:
    err = _err(sql)
    assert err is not None
    assert bad in json.loads(err)["error"]


def test_no_manifest_list_means_no_restriction() -> None:
    assert allowed_tables_error([], SCHEMA, "SELECT * FROM anything") is None
