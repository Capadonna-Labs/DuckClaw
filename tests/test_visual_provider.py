"""Tests visual_provider resolution."""

from __future__ import annotations

import pytest

from duckclaw.forge.skills.visual_provider import (
    default_visual_provider,
    resolve_visual_provider,
)


class _CfgDb:
    def __init__(self, value: str = ""):
        self.value = value

    def query(self, sql: str):
        import json
        if self.value:
            return json.dumps([{"value": self.value}])
        return json.dumps([])

    def execute(self, sql: str) -> None:
        pass


def test_default_local_when_only_comfy_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    monkeypatch.delenv("FAL_KEY", raising=False)
    assert default_visual_provider() == "local"


def test_default_fal_when_both_env_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:8188")
    monkeypatch.setenv("FAL_KEY", "test-key")
    assert default_visual_provider() == "fal"


def test_default_fal_when_only_fal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMFYUI_API_URL", raising=False)
    monkeypatch.setenv("FAL_KEY", "test-key")
    assert default_visual_provider() == "fal"


def test_resolve_chat_override_fal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-key")
    db = _CfgDb("fal")
    assert resolve_visual_provider(db, "chat-1") == "fal"