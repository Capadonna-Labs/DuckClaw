"""Normalización de historial para el API Gateway (Redis)."""

from __future__ import annotations

import sys
from pathlib import Path

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.chat_history import (  # noqa: E402
    compute_turn_user_index,
    normalize_history_item,
    normalize_history_list,
)


def test_normalize_history_item_user_assistant() -> None:
    assert normalize_history_item({"role": "user", "content": "hola"}) == {"role": "user", "content": "hola"}
    assert normalize_history_item({"role": "assistant", "content": "x"}) == {"role": "assistant", "content": "x"}
    assert normalize_history_item({"role": "human", "content": "z"}) == {"role": "user", "content": "z"}


def test_normalize_history_item_rejects_system() -> None:
    assert normalize_history_item({"role": "system", "content": "nope"}) is None


def test_normalize_history_item_assistant_strips_telegram_escape() -> None:
    out = normalize_history_item({"role": "assistant", "content": r"hola\!"})
    assert out == {"role": "assistant", "content": "hola!"}


def test_normalize_history_list_filters() -> None:
    out = normalize_history_list(
        [
            {"role": "user", "content": "a"},
            {"role": "invalid", "content": "x"},
            {"role": "assistant", "content": "b"},
        ]
    )
    assert out == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]


def test_compute_turn_user_index_under_cap() -> None:
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "A"}]
    assert compute_turn_user_index(hist) == 2


def test_compute_turn_user_index_at_max_msgs_cap(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_MAX_MSGS", "4")
    # 2 users + 2 assistants = techo; el nuevo user desplaza el par viejo → sigue siendo user #2
    hist = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "A"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "B"},
    ]
    assert compute_turn_user_index(hist) == 2
    # Fórmula ingenua prior+1 daría 3 y desalinea Tool Usage en el cliente.
    assert sum(1 for item in hist if item.get("role") == "user") + 1 == 3


def test_history_keeps_message_times_and_stamps_only_the_new_turn() -> None:
    """Each message carries when it was sent (the UI shows it on swipe); history saved
    before timestamps existed never gets a fake "now" on its old messages."""
    from core.chat_history import normalize_history_list, stamp_new_history_items

    legacy = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    turn = [{"role": "user", "content": "c", "ts": "2026-10-19T04:00:00Z"}, {"role": "assistant", "content": "d"}]
    out = stamp_new_history_items(normalize_history_list(legacy + turn))
    assert [m.get("ts") for m in out[:2]] == [None, None]
    assert out[2]["ts"] == "2026-10-19T04:00:00Z" and out[3]["ts"].endswith("Z")
    # Next save: already-stamped messages keep their time.
    again = stamp_new_history_items(normalize_history_list(out))
    assert again[2]["ts"] == "2026-10-19T04:00:00Z" and again[3]["ts"] == out[3]["ts"]
