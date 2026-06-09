import pytest
from pydantic import ValidationError

from duckclaw_sensory_node.models import STTRequest, TTSRequest


def test_tts_rejects_reference_audio_injection():
    with pytest.raises(ValidationError):
        TTSRequest(
            text="hola",
            voice_id="leila_assistant",
            ref_audio="evil.wav",  # type: ignore[call-arg]
        )


def test_tts_request_valid():
    req = TTSRequest(text="hola", voice_id="finanz_alert")
    assert req.speed == 1.0


def test_stt_request_defaults():
    req = STTRequest(audio_base64="AAAA")
    assert req.language_hint == "es"
