from __future__ import annotations

import duckclaw

from duckclaw.graphs.on_the_fly_commands import execute_model, execute_models


def test_execute_model_accepts_gemini_provider() -> None:
    db = duckclaw.DuckClaw(":memory:")
    out = execute_model(db, "chat1", "provider=gemini")
    assert "Modelo actualizado" in out
    current = execute_model(db, "chat1", "")
    assert "provider: gemini" in current
    assert "model: gemini-2.0-flash" in current


def test_execute_models_gemini_lists_models(monkeypatch) -> None:
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return (
                b'{"models":[{"name":"models/gemini-2.0-flash","supportedGenerationMethods":["generateContent"]},'
                b'{"name":"models/gemini-1.5-pro","supportedGenerationMethods":["generateContent"]},'
                b'{"name":"models/embedding-001","supportedGenerationMethods":["embedContent"]}]}'
            )

    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    db = duckclaw.DuckClaw(":memory:")
    out = execute_models(db, "chat1", "provider=gemini")
    assert "Modelos Gemini disponibles (2)" in out
    assert "- gemini-2.0-flash" in out
    assert "- gemini-1.5-pro" in out


def test_execute_models_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    db = duckclaw.DuckClaw(":memory:")
    out = execute_models(db, "chat1", "provider=gemini")
    assert "GOOGLE_API_KEY" in out
