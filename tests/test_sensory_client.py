"""Tests for gateway sensory HTTP client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()

import core.sensory_client as sensory_mod
from core.sensory_client import (
    SensoryForbidden,
    SensoryUnavailable,
    resolve_voice_id_for_worker,
    sensory_enabled,
    synthesize_text,
    transcribe_audio_base64,
    tts_snippet_for_reply,
)


@pytest.fixture(autouse=True)
def _sensory_env(monkeypatch):
    monkeypatch.setenv("DUCKCLAW_SENSORY_BASE_URL", "http://100.99.72.63:8001")


def test_sensory_enabled():
    assert sensory_enabled() is True


def test_resolve_voice_id_default():
    assert resolve_voice_id_for_worker("unknown") == "default"


def test_resolve_voice_id_configured_worker(monkeypatch):
    monkeypatch.setenv(
        "DUCKCLAW_TTS_VOICE_MAP",
        json.dumps({"researcher": "narrator_main"}),
    )
    assert resolve_voice_id_for_worker("researcher") == "narrator_main"


def test_tts_snippet_strips_worker_instance_header():
    raw = (
        "researcher 1 · **MAR 18:05 COT** · Seguimiento\n"
        "---\n"
        "## Guerra USA-Irán\n"
        "Conflicto activo desde febrero."
    )
    out = tts_snippet_for_reply(raw)
    assert "researcher" not in out.lower()
    assert "Conflicto activo" in out
    assert "---" not in out


def test_resolve_voice_id_map(monkeypatch):
    monkeypatch.setenv(
        "DUCKCLAW_TTS_VOICE_MAP",
        json.dumps({"worker_a": "voice_a", "default": "voice_default"}),
    )
    assert resolve_voice_id_for_worker("worker_a") == "voice_a"
    assert resolve_voice_id_for_worker("other") == "voice_default"


def _fake_client(post_json: dict, *, status: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json = MagicMock(return_value=post_json)
    mock_resp.text = json.dumps(post_json)
    mock_post = AsyncMock(return_value=mock_resp)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        post = mock_post

    return FakeClient, mock_post


def test_transcribe_ok():
    FakeClient, _ = _fake_client(
        {"text": "hola", "processing_time_ms": 42.0, "language_detected": "es"},
    )

    async def _run():
        with patch.object(sensory_mod.httpx, "AsyncClient", return_value=FakeClient()):
            return await transcribe_audio_base64("AAAA")

    result = asyncio.run(_run())
    assert result.text == "hola"


def test_transcribe_503():
    FakeClient, _ = _fake_client({"detail": "fail"}, status=503)

    async def _run():
        with patch.object(sensory_mod.httpx, "AsyncClient", return_value=FakeClient()):
            await transcribe_audio_base64("AAAA")

    with pytest.raises(SensoryUnavailable):
        asyncio.run(_run())


def test_synthesize_403():
    FakeClient, _ = _fake_client({"detail": "forbidden"}, status=403)

    async def _run():
        with patch.object(sensory_mod.httpx, "AsyncClient", return_value=FakeClient()):
            await synthesize_text("hola", "voice_default")

    with pytest.raises(SensoryForbidden):
        asyncio.run(_run())
