"""Tests for env-driven voice_id resolution (no vertical defaults in code)."""

from duckclaw_pipecat.voice_id_resolver import resolve_sensory_voice_id, resolve_voice_id_for_worker


def test_resolve_voice_id_default_when_map_empty() -> None:
    assert resolve_voice_id_for_worker("any-worker", default_voice_id="default") == "default"


def test_resolve_voice_id_worker_map() -> None:
    mapping = '{"worker_a":"voice_alpha","default":"voice_default"}'
    assert resolve_voice_id_for_worker("worker_a", voice_map_json=mapping) == "voice_alpha"
    assert resolve_voice_id_for_worker("unknown", voice_map_json=mapping) == "voice_default"


def test_resolve_sensory_voice_id_app_state_override() -> None:
    vid = resolve_sensory_voice_id(
        worker_id="worker_a",
        app_state={"voice_id": "custom_voice"},
        default_voice_id="default",
        voice_map_json='{"worker_a":"voice_alpha"}',
    )
    assert vid == "custom_voice"


def test_resolve_sensory_voice_id_worker_from_app_state() -> None:
    vid = resolve_sensory_voice_id(
        worker_id="stale",
        app_state={"worker_id": "worker_b"},
        default_voice_id="default",
        voice_map_json='{"worker_b":"voice_beta"}',
    )
    assert vid == "voice_beta"
