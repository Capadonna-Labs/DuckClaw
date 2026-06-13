from __future__ import annotations

from duckclaw.github.workflow import github_pr_workflow_resolved_intent
from duckclaw.quant.runtime_policy import (
    _quant_extract_tickers,
    quant_allows_reddit_anchor_force,
)
from duckclaw.workers.db_intent_policy import (
    explicit_duckdb_schema_request,
    incoming_is_schema_query_heuristic,
    incoming_is_table_content_query,
)
from duckclaw.workers.db_runtime import truncate_read_sql_result_for_llm


def test_db_intent_distinguishes_schema_table_content_and_lone_url() -> None:
    assert explicit_duckdb_schema_request("que tablas tengo en duckdb?") is True
    assert incoming_is_table_content_query("qué hay en la tabla movimientos?") is True
    assert incoming_is_schema_query_heuristic("https://example.com/estructura") is False


def test_quant_policy_tickers_and_reddit_anchor() -> None:
    assert _quant_extract_tickers("TAREA: genera señal para AAPL y MSFT") == ["AAPL", "MSFT"]
    assert quant_allows_reddit_anchor_force(
        "quant_trader",
        "https://reddit.com/r/stocks/s/abc123",
        "https://reddit.com/r/stocks/s/abc123",
        is_quant_trading_worker=True,
    )


def test_github_pr_intent_lives_outside_factory() -> None:
    assert github_pr_workflow_resolved_intent([], "crea un pull request con este patch")
    assert not github_pr_workflow_resolved_intent([], "cancela la señal pendiente")


def test_db_runtime_truncates_large_read_sql_payload(monkeypatch) -> None:
    monkeypatch.setattr("duckclaw.workers.db_runtime.READ_SQL_MAX_RESPONSE_CHARS", 8)
    out = truncate_read_sql_result_for_llm("x" * 20)
    assert "warning" in out
    assert "omitted_chars" in out
