"""Live voice turns send only recent history to the graph; other turns are untouched."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api-gateway"))

from core.chat_graph_runner import _trim_history_for_live_voice  # noqa: E402


@dataclass(frozen=True)
class _P:
    message: str
    history_for_graph: list = field(default_factory=list)


def _hist(n: int) -> list[dict]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 4000} for i in range(n)]


def test_voice_turn_trims_history(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VOICE_HISTORY_TOKENS", "3000")
    out = _trim_history_for_live_voice(_P("[Canal voz en vivo: ...]\n\nhola", _hist(40)))
    assert 0 < len(out.history_for_graph) <= 4
    assert out.history_for_graph[0]["role"] == "user"


def test_text_turn_keeps_history() -> None:
    p = _P("hola", _hist(40))
    assert _trim_history_for_live_voice(p) is p
