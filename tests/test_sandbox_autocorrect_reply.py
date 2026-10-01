"""Sandbox auto-correct must never run the AIMessage repr as code."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from duckclaw.graphs.sandbox import _corrected_code_from_llm


def test_empty_content_is_not_turned_into_repr_code() -> None:
    # Reasoning model spent the whole budget: content '' + completion_tokens == max.
    msg = AIMessage(content="", response_metadata={"token_usage": {"completion_tokens": 2048}})
    assert _corrected_code_from_llm(msg) == ""


def test_truncated_reply_is_discarded() -> None:
    msg = AIMessage(content="import numpy as np\nfor i in", response_metadata={"finish_reason": "length"})
    assert _corrected_code_from_llm(msg) == ""


def test_fenced_code_and_block_lists_are_extracted() -> None:
    assert _corrected_code_from_llm(AIMessage(content="```python\nprint(1)\n```")) == "print(1)"
    blocks = AIMessage(content=[{"type": "text", "text": "print(2)"}])
    assert _corrected_code_from_llm(blocks) == "print(2)"
    assert _corrected_code_from_llm("print(3)") == "print(3)"


def test_sandbox_timeout_ceiling_is_configurable(monkeypatch) -> None:
    """Long-running agents: the per-run ceiling is no longer a fixed 600 s."""
    from duckclaw.forge.schema import SecurityPolicy
    from duckclaw.graphs import sandbox as sb

    monkeypatch.delenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MIN_TIMEOUT_SEC", "1800")
    pol = SecurityPolicy()  # zero-trust default: 30 s
    assert sb._sandbox_effective_timeout_sec(pol) == 1800  # env floor, above the old 600 cap
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", "900")
    assert sb._sandbox_effective_timeout_sec(pol) == 900  # still bounded by the ceiling
    assert SecurityPolicy(max_execution_time_seconds=7200).max_execution_time_seconds == 7200
