from __future__ import annotations

from duckclaw.github.workflow import _github_parse_push_files_success, github_pr_workflow_resolved_intent
from duckclaw.quant.runtime_policy import (
    _quant_summarize_allows_forced_ohlcv_fetch,
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


def test_quant_context_summary_ohlcv_fetch_is_db_policy_gated(monkeypatch) -> None:
    from types import SimpleNamespace

    from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy

    capability = WorkerCapability(
        capability_id="cap_quant_trading",
        name="quant_trading",
        kind="runtime_policy",
        provider="duckclaw",
        permission="use",
        config={},
        policy={"allow_ohlcv_on_context_summary": True},
        quota={},
    )
    spec = SimpleNamespace(
        runtime_policy=WorkerRuntimePolicy(
            worker_id="Quant-Trader",
            identity=None,
            capabilities=(capability,),
        )
    )

    assert _quant_summarize_allows_forced_ohlcv_fetch(
        "Trae velas OHLCV de SPY",
        "Quant-Trader",
        spec=spec,
        is_quant_trading_worker=True,
    )

    monkeypatch.setenv("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY", "true")
    assert not _quant_summarize_allows_forced_ohlcv_fetch(
        "Trae velas OHLCV de SPY",
        "Quant-Trader",
        spec=SimpleNamespace(runtime_policy=None),
        is_quant_trading_worker=True,
    )


def test_github_pr_intent_lives_outside_factory() -> None:
    assert github_pr_workflow_resolved_intent([], "crea un pull request con este patch")
    assert not github_pr_workflow_resolved_intent([], "cancela la señal pendiente")


def test_github_workflow_repo_defaults_can_come_from_db_policy() -> None:
    content = '{"ref": "refs/heads/feat/backend-cleanup"}'

    assert _github_parse_push_files_success(
        content,
        {"owner": "duckclaw-labs", "repo": "control-plane"},
    ) == ("duckclaw-labs", "control-plane", "feat/backend-cleanup")


def test_db_runtime_truncates_large_read_sql_payload(monkeypatch) -> None:
    monkeypatch.setattr("duckclaw.workers.db_runtime.READ_SQL_MAX_RESPONSE_CHARS", 8)
    out = truncate_read_sql_result_for_llm("x" * 20)
    assert "warning" in out
    assert "omitted_chars" in out
