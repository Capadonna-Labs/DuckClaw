"""Tests for post-turn chat follow-up suggestions (generate_followup_suggestions)."""

from __future__ import annotations

from types import SimpleNamespace

from duckclaw.commands.chat_suggestions import (
    _SYSTEM_PROMPT,
    _parse_suggestions_payload,
    generate_followup_suggestions,
)


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


def test_system_prompt_allows_optional_prudent_proceed() -> None:
    assert "Procede" in _SYSTEM_PROMPT
    assert "pruden" in _SYSTEM_PROMPT.lower()
    assert "siguiente paso operativo" in _SYSTEM_PROMPT or "siguiente paso" in _SYSTEM_PROMPT


def test_parse_payload_object_with_recommended_index() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["a","b","c"],"recommended_index":2}'
    )
    assert out == {"suggestions": ["a", "b", "c"], "recommended_index": 2}


def test_parse_payload_allows_proceed_as_free_chip() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["Procede","¿Qué riesgo queda?","¿Falta TP/SL?"],'
        '"recommended_index":0}'
    )
    assert out["suggestions"][0] == "Procede"
    assert out["recommended_index"] == 0


def test_parse_payload_legacy_array_defaults_index_zero() -> None:
    out = _parse_suggestions_payload('["a", "b", "c"]')
    assert out == {"suggestions": ["a", "b", "c"], "recommended_index": 0}


def test_parse_payload_clamps_bad_index() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["a","b"],"recommended_index":99}'
    )
    assert out["recommended_index"] == 0


def test_generate_followup_suggestions_parses_json_object(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM(
            '{"suggestions":["¿Puedes profundizar?", "Resume en 3 puntos", "¿Qué sigue?"],'
            '"recommended_index":1}'
        ),
    )
    out = generate_followup_suggestions(
        object(),
        "chat-1",
        last_user_text="hola",
        last_assistant_text="Respuesta del asistente",
    )
    assert out["suggestions"] == [
        "¿Puedes profundizar?",
        "Resume en 3 puntos",
        "¿Qué sigue?",
    ]
    assert out["recommended_index"] == 1


def test_generate_followup_suggestions_strips_markdown_fence(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM('```json\n["a", "b", "c"]\n```'),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out["suggestions"] == ["a", "b", "c"]
    assert out["recommended_index"] == 0


def test_generate_followup_suggestions_caps_to_three(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM('["a", "b", "c", "d", "e"]'),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out["suggestions"] == ["a", "b", "c"]


def test_generate_followup_suggestions_malformed_json_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM("no soy json"),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == {"suggestions": [], "recommended_index": 0}


def test_generate_followup_suggestions_llm_exception_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)

    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", _raise)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == {"suggestions": [], "recommended_index": 0}


def test_generate_followup_suggestions_none_llm_returns_empty(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", lambda *a, **k: None)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out == {"suggestions": [], "recommended_index": 0}


def test_generate_followup_suggestions_empty_assistant_text_short_circuits(monkeypatch) -> None:
    def _fail(*a, **k):
        raise AssertionError("no debería llamar LLM")

    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", _fail)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="  "
    )
    assert out == {"suggestions": [], "recommended_index": 0}


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
    assert out == {"suggestions": [], "recommended_index": 0}
