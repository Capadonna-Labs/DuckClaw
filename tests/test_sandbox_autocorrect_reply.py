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
