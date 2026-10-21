"""Smoke tests for Observabilidad 2.0 structured logging."""

from __future__ import annotations

import logging


def test_duckclaw_log_filter_injects_context() -> None:
    from duckclaw.utils.logger import (
        DuckClawLogFilter,
        DuckClawStructuredFormatter,
        ctx_chat,
        ctx_tenant,
        ctx_worker,
        reset_log_context,
        set_log_context,
    )

    reset_log_context()
    set_log_context(tenant_id="acme", worker_id="platform-orchestrator", chat_id="12345")
    fmt = DuckClawStructuredFormatter()
    flt = DuckClawLogFilter()
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
    assert flt.filter(record) is True
    line = fmt.format(record)
    assert "acme" in line and "platform-orchestrator" in line and "12345" in line and "hello" in line
    reset_log_context()


def test_extract_usage_from_messages_empty() -> None:
    from duckclaw.utils.logger import extract_usage_from_messages

    assert extract_usage_from_messages(None) is None
    assert extract_usage_from_messages([]) is None


def test_extract_usage_from_messages_sums_all_ai_messages() -> None:
    from duckclaw.utils.logger import extract_usage_from_messages
    from langchain_core.messages import AIMessage

    msgs = [
        AIMessage(content="a", usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}),
        AIMessage(content="b", usage_metadata={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220}),
    ]
    got = extract_usage_from_messages(msgs)
    assert got == {"input_tokens": 300, "output_tokens": 30, "total_tokens": 330}


def test_extract_usage_reports_cached_prompt_tokens_only_when_the_provider_does() -> None:
    from duckclaw.utils.logger import extract_usage_from_messages
    from langchain_core.messages import AIMessage

    cached = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110, "input_token_details": {"cache_read": 80}}
    miss = {"input_tokens": 200, "output_tokens": 20, "total_tokens": 220, "input_token_details": {"cache_read": 0}}
    got = extract_usage_from_messages([AIMessage(content="a", usage_metadata=cached), AIMessage(content="b", usage_metadata=miss)])
    assert got == {"input_tokens": 300, "output_tokens": 30, "total_tokens": 330, "cached_tokens": 80}
    deepseek = AIMessage(content="c", response_metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 5, "prompt_cache_hit_tokens": 40}})
    assert extract_usage_from_messages([deepseek])["cached_tokens"] == 40
    assert "cached_tokens" not in extract_usage_from_messages([AIMessage(content="d", usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})])


def test_log_tool_execution_sync_timing() -> None:
    from duckclaw.utils.logger import log_tool_execution_sync

    @log_tool_execution_sync(name="dummy_tool")
    def _f(x: int) -> int:
        return x + 1

    assert _f(1) == 2


