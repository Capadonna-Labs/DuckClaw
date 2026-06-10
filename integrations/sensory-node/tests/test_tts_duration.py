"""TTS engine duration/num_steps config (no MLX inference)."""

from __future__ import annotations

import pytest

from duckclaw_sensory_node.engines.tts import _max_duration_sec, _num_steps


def test_max_duration_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_SENSORY_TTS_MAX_DURATION_SEC", raising=False)
    assert _max_duration_sec() == 90.0


def test_max_duration_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_SENSORY_TTS_MAX_DURATION_SEC", "120")
    assert _max_duration_sec() == 120.0


def test_num_steps_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_SENSORY_TTS_NUM_STEPS", "48")
    assert _num_steps() == 48
