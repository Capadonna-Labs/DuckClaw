"""ElevenLabs voice provider in the gateway sensory client (no network: httpx MockTransport)."""

from __future__ import annotations

import asyncio
import base64
import io
import wave

import httpx
import pytest

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()

import core.sensory_client as sc  # noqa: E402


@pytest.fixture
def eleven(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["xi-api-key"] == "k"
        if req.url.path == "/v1/voices":
            return httpx.Response(200, json={"voices": [{"voice_id": "v_first"}, {"voice_id": "v2"}]})
        if req.url.path.startswith("/v1/text-to-speech/"):
            return httpx.Response(200, content=b"\x00\x01" * 22050)  # 1 s of 16-bit PCM
        if req.url.path == "/v1/speech-to-text":
            return httpx.Response(200, json={"text": " hola mundo ", "language_code": "spa"})
        return httpx.Response(404)

    real = httpx.AsyncClient
    monkeypatch.setattr(sc.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.delenv("DUCKCLAW_SENSORY_BASE_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_VOICE_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_ELEVENLABS_VOICE_ID", raising=False)
    sc._elevenlabs_voice_cache.clear()
    return calls


def test_enabled_without_mac_mini(eleven) -> None:
    assert sc.sensory_enabled() is True
    health = asyncio.run(sc.sensory_health())
    assert health and health["provider"] == "elevenlabs" and health["tts_loaded"] is True


def test_synthesize_returns_playable_wav_with_account_voice(eleven) -> None:
    out = asyncio.run(sc.synthesize_text("Hola", "default"))
    assert out.audio_format == "wav" and abs(out.duration_sec - 1.0) < 1e-6
    with wave.open(io.BytesIO(base64.b64decode(out.audio_base64))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (22050, 1, 22050)
    tts = [c for c in eleven if "text-to-speech" in c.url.path][0]
    assert tts.url.path.endswith("/v_first") and tts.url.params["output_format"] == "pcm_22050"


def test_transcribe_uses_scribe(eleven) -> None:
    b64 = base64.b64encode(b"fake-ogg").decode()
    out = asyncio.run(sc.transcribe_audio_base64(b64, language_hint="es"))
    assert out.text == "hola mundo" and out.language_detected == "spa"


def test_provider_override_keeps_mac_mini_path(eleven, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VOICE_PROVIDER", "sensory")
    assert sc._elevenlabs_key() == ""
    assert sc.sensory_enabled() is False  # no DUCKCLAW_SENSORY_BASE_URL in this test
