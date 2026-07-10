"""Fly command /approve-model."""
from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.commands.hitl import execute_approve_model


def test_execute_approve_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    out = execute_approve_model(None, "chat-1", "packages/agents/train/gemma4/adapters_lora_yaml")
    assert "MLX-Inference" in out
    assert "adapters_lora_yaml" in out


def test_execute_approve_model_missing_args() -> None:
    assert "Uso:" in execute_approve_model(None, "c", "")
