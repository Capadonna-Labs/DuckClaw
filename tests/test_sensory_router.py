"""Gateway sensory proxy router tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def sensory_app(monkeypatch):
    monkeypatch.setenv("DUCKCLAW_SENSORY_BASE_URL", "http://100.99.72.63:8001")
    from routers.sensory import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_not_configured(monkeypatch):
    monkeypatch.delenv("DUCKCLAW_SENSORY_BASE_URL", raising=False)
    from routers.sensory import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/v1/sensory/health")
    assert r.status_code == 503


def test_transcribe_proxy(sensory_app):
    import routers.sensory as sensory_router

    async def _fake_transcribe(*_a, **_k):
        from core.sensory_client import STTResult

        return STTResult(text="ok", processing_time_ms=1.0, language_detected="es")

    with patch.object(sensory_router, "transcribe_audio_base64", side_effect=_fake_transcribe):
        r = sensory_app.post(
            "/api/v1/sensory/transcribe",
            json={"audio_base64": "QUFB", "language_hint": "es"},
        )
    assert r.status_code == 200
    assert r.json()["text"] == "ok"


def test_synthesize_rejects_ref_audio(sensory_app):
    r = sensory_app.post(
        "/api/v1/sensory/synthesize",
        json={"text": "hola", "voice_id": "leila_assistant", "ref_audio": "x.wav"},
    )
    assert r.status_code == 422
