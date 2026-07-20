from pathlib import Path

import pytest
from pydantic import ValidationError

from duckclaw_sensory_node.models import STTRequest, TTSRequest


_BANNED_CORE_VOICE_IDS = {
    "leila_assistant",
    "finanz_alert",
    "quant_trader_brief",
}


def test_tts_rejects_reference_audio_injection():
    with pytest.raises(ValidationError):
        TTSRequest(
            text="hola",
            voice_id="tenant_voice_alpha",
            ref_audio="evil.wav",  # type: ignore[call-arg]
        )


def test_tts_request_accepts_manifest_owned_voice_ids_without_python_allowlist():
    req = TTSRequest(text="hola", voice_id="tenant_voice_alpha")
    assert req.speed == 1.0


def test_stt_request_defaults():
    req = STTRequest(audio_base64="AAAA")
    assert req.language_hint == "es"


def test_sensory_voice_defaults_do_not_embed_vertical_voice_ids():
    repo = Path(__file__).resolve().parents[3]
    checked_paths = [
        repo / "integrations/sensory-node/scripts/prepare_voice.py",
        repo / "integrations/sensory-node/scripts/prepare_default_voices.sh",
        repo / "integrations/sensory-node/scripts/check_tts_amplitude.py",
        repo / "integrations/sensory-node/scripts/test_live_synthesize.sh",
        repo / "integrations/sensory-node/voices/manifest.json",
        repo / "integrations/sensory-node/voices/README.md",
    ]

    for path in checked_paths:
        body = path.read_text(encoding="utf-8")
        for voice_id in _BANNED_CORE_VOICE_IDS:
            assert voice_id not in body, f"{voice_id} leaked into {path}"
