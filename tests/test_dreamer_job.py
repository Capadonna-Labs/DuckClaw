"""Tests unitarios Dreamer: parser JSON, exclusiones, golden heurístico, compactación lógica."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_AGENTS_SRC = _REPO / "packages" / "agents" / "src"
if str(_AGENTS_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENTS_SRC))

from duckclaw.graphs.dreamer_job import (  # noqa: E402
    MAX_INSIGHTS_PER_RUN,
    _deep_phase_allows_compaction,
    _parse_insights_json,
    is_golden_turn,
)


def test_parse_insights_json_plain() -> None:
    raw = '{"insights":[{"topic":"A","insight":"B","confidence":0.9}]}'
    out = _parse_insights_json(raw)
    assert len(out) == 1
    assert out[0]["topic"] == "A"
    assert out[0]["insight"] == "B"
    assert out[0]["confidence"] == 0.9


def test_parse_insights_json_fenced() -> None:
    raw = """Aquí va\n```json\n{"insights":[{"topic":"x","insight":"y","confidence":0.6}]}\n```"""
    out = _parse_insights_json(raw)
    assert out[0]["topic"] == "x"


def test_is_golden_turn_exclusion() -> None:
    assert is_golden_turn("user", "texto suficientemente largo para prueba") is True
    assert is_golden_turn("user", "texto con Ceguera Sensorial en el medio largo") is False
    assert is_golden_turn("assistant", "texto suficientemente largo para prueba") is False


def test_deep_phase_allows_compaction() -> None:
    assert _deep_phase_allows_compaction([], True) is True
    assert _deep_phase_allows_compaction([{"topic": "t", "insight": "i", "confidence": 0.9}], True) is True
    assert _deep_phase_allows_compaction([{"topic": "t", "insight": "i", "confidence": 0.9}], False) is False


def test_max_insights_cap_constants() -> None:
    assert MAX_INSIGHTS_PER_RUN == 20
