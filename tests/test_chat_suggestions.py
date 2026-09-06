"""Tests for post-turn chat follow-up suggestions (generate_followup_suggestions)."""

from __future__ import annotations

from types import SimpleNamespace

from duckclaw.commands.chat_suggestions import generate_followup_suggestions


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages):  # noqa: ANN001
        return SimpleNamespace(content=self._content)


def _patch_triplet(monkeypatch) -> None:
    monkeypatch.setattr(
        "duckclaw.commands.chat_suggestions._effective_llm_triplet_for_chat_ui",
        lambda db, chat_id: ("openai", "gpt-4o-mini", ""),
    )


def test_generate_followup_suggestions_parses_json_array(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM('["¿Puedes profundizar?", "Resume en 3 puntos", "¿Qué sigue?"]'),
    )
    out = generate_followup_suggestions(
        object(),
        "chat-1",
        last_user_text="hola",
        last_assistant_text="Respuesta del asistente",
    )
    assert out == ["¿Puedes profundizar?", "Resume en 3 puntos", "¿Qué sigue?"]


def test_generate_followup_suggestions_strips_markdown_fence(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM('```json\n["a", "b", "c"]\n```'),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == ["a", "b", "c"]


def test_generate_followup_suggestions_caps_to_three(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM('["a", "b", "c", "d", "e"]'),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == ["a", "b", "c"]


def test_generate_followup_suggestions_malformed_json_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM("no soy json"),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == []


def test_generate_followup_suggestions_llm_exception_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)

    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", _raise)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == []


def test_generate_followup_suggestions_none_llm_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", lambda *a, **k: None)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == []


def test_generate_followup_suggestions_empty_assistant_text_short_circuits(monkeypatch) -> None:
    _patch_triplet(monkeypatch)

    def _fail_if_called(*a, **k):
        raise AssertionError("build_llm no debería llamarse sin texto del asistente")

    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", _fail_if_called)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="   "
    )
    assert out == []


def test_generate_followup_suggestions_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CHAT_SUGGESTIONS_ENABLED", "0")

    def _fail_if_called(db, chat_id):
        raise AssertionError("no debería resolver triplete con el feature apagado")

    monkeypatch.setattr(
        "duckclaw.commands.chat_suggestions._effective_llm_triplet_for_chat_ui", _fail_if_called
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == []
