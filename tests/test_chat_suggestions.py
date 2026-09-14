"""Tests for post-turn chat follow-up suggestions (generate_followup_suggestions)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from duckclaw.commands.chat_suggestions import (
    _DO_NOT_PROCEED_CHIP,
    _PROCEED_CHIP,
    _SYSTEM_PROMPT,
    _normalize_proceed_triplet,
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


def test_system_prompt_documents_proceed_pair_and_prudent_proceed() -> None:
    assert _PROCEED_CHIP in _SYSTEM_PROMPT
    assert _DO_NOT_PROCEED_CHIP in _SYSTEM_PROMPT
    assert "pruden" in _SYSTEM_PROMPT.lower()
    assert "recommended_index" in _SYSTEM_PROMPT


def test_normalize_defaults_recommended_to_no_proceed() -> None:
    out = _normalize_proceed_triplet("¿Qué TP/SL conviene?", recommended_raw=99)
    assert out == {
        "suggestions": [_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP, "¿Qué TP/SL conviene?"],
        "recommended_index": 1,
    }


def test_normalize_allows_proceed_when_index_zero() -> None:
    out = _normalize_proceed_triplet("Detalle el plan", recommended_raw=0)
    assert out["suggestions"][0] == _PROCEED_CHIP
    assert out["recommended_index"] == 0


def test_parse_payload_third_suggestion_object() -> None:
    out = _parse_suggestions_payload(
        '{"third_suggestion":"¿Qué riesgo queda?","recommended_index":1}'
    )
    assert out["suggestions"] == [_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP, "¿Qué riesgo queda?"]
    assert out["recommended_index"] == 1


def test_parse_payload_object_with_recommended_proceed() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["Procede","No procede","¿Listo para corregir?"],'
        '"recommended_index":0}'
    )
    assert out["suggestions"][0] == _PROCEED_CHIP
    assert out["suggestions"][1] == _DO_NOT_PROCEED_CHIP
    assert out["suggestions"][2] == "¿Listo para corregir?"
    assert out["recommended_index"] == 0


def test_parse_payload_legacy_array_forces_proceed_pair() -> None:
    out = _parse_suggestions_payload('["a", "b", "c"]')
    assert out["suggestions"] == [_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP, "c"]
    assert out["recommended_index"] == 1


def test_parse_payload_clamps_bad_index_to_no_proceed() -> None:
    out = _parse_suggestions_payload(
        '{"third_suggestion":"x","recommended_index":99}'
    )
    assert out["recommended_index"] == 1


def test_generate_followup_suggestions_parses_json_object(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM(
            '{"third_suggestion":"¿Qué TP/SL conviene?","recommended_index":1}'
        ),
    )
    out = generate_followup_suggestions(
        object(),
        "chat-1",
        last_user_text="hola",
        last_assistant_text="Respuesta del asistente",
    )
    assert out["suggestions"] == [
        _PROCEED_CHIP,
        _DO_NOT_PROCEED_CHIP,
        "¿Qué TP/SL conviene?",
    ]
    assert out["recommended_index"] == 1


def test_generate_followup_suggestions_strips_markdown_fence(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM(
            '```json\n{"third_suggestion":"c","recommended_index":0}\n```'
        ),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert out["suggestions"] == [_PROCEED_CHIP, _DO_NOT_PROCEED_CHIP, "c"]
    assert out["recommended_index"] == 0


def test_generate_followup_suggestions_caps_third_length(monkeypatch) -> None:
    _patch_triplet(monkeypatch)
    long_third = "x" * 200
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _FakeLLM(
            json.dumps({"third_suggestion": long_third, "recommended_index": 1})
        ),
    )
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="ok"
    )
    assert len(out["suggestions"][2]) <= 80


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
