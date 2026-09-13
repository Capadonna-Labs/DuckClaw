"""Contextvar override tras compactar historial a mitad de turno."""

from __future__ import annotations

from duckclaw.forge.skills.chat_history_compact_context import (
    peek_compacted_chat_history,
    set_compacted_chat_history,
    take_compacted_chat_history,
)


def test_set_take_compacted_chat_history_round_trip() -> None:
    set_compacted_chat_history(
        [
            {"role": "user", "content": "hola"},
            {"role": "human", "content": "sigue"},
            {"role": "assistant", "content": "ok"},
            {"role": "system", "content": "nope"},
            {"role": "user", "content": "  "},
        ]
    )
    assert peek_compacted_chat_history() == [
        {"role": "user", "content": "hola"},
        {"role": "user", "content": "sigue"},
        {"role": "assistant", "content": "ok"},
    ]
    taken = take_compacted_chat_history()
    assert taken == [
        {"role": "user", "content": "hola"},
        {"role": "user", "content": "sigue"},
        {"role": "assistant", "content": "ok"},
    ]
    assert take_compacted_chat_history() is None
    assert peek_compacted_chat_history() is None


def test_set_compacted_chat_history_none_clears() -> None:
    set_compacted_chat_history([{"role": "user", "content": "x"}])
    set_compacted_chat_history(None)
    assert take_compacted_chat_history() is None
