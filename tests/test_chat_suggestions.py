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


def test_system_prompt_prioritizes_answering_assistant_questions() -> None:
    low = _SYSTEM_PROMPT.lower()
    assert "prioridad 1" in low
    assert "pregunta directa" in low
    assert "respondiendo a esa pregunta" in low
    assert "documentarlo como issue" in low or "documentalo como issue" in low
    assert "prohibido" in low


def test_system_prompt_prefers_useful_angles_over_next_step_ops() -> None:
    """Guardrail: when not answering a question, chips must not only push confirm/execute."""
    lower = _SYSTEM_PROMPT.lower()
    assert "prioridad 2" in lower
    assert "confirma las ocas" in lower or "ejecuta el batch" in lower
    assert "riesgo" in lower or "distancias" in lower
    assert "recommended_index" in lower


def test_system_prompt_allows_optional_prudent_proceed() -> None:
    low = _SYSTEM_PROMPT.lower()
    assert "procede" in low
    assert "excepción prudente" in low or "excepcion prudente" in low

def test_parse_payload_object_with_recommended_index() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["a","b","c"],"recommended_index":2}'
    )
    assert out == {"suggestions": ["a", "b", "c"], "recommended_index": 2}


def test_parse_payload_legacy_array_defaults_index_zero() -> None:
    out = _parse_suggestions_payload('["a", "b", "c"]')
    assert out == {"suggestions": ["a", "b", "c"], "recommended_index": 0}


def test_parse_payload_clamps_bad_index() -> None:
    out = _parse_suggestions_payload(
        '{"suggestions":["a","b"],"recommended_index":99}'
    )
    assert out["recommended_index"] == 0


def test_generate_followup_suggestions_human_prompt_flags_assistant_question(
    monkeypatch,
) -> None:
    """When the worker asks something, the human prompt must steer chips to reply."""
    _patch_triplet(monkeypatch)
    captured: list[Any] = []

    class _CaptureLLM:
        def invoke(self, messages):  # noqa: ANN001
            captured.extend(messages)
            return SimpleNamespace(
                content='{"suggestions":["Sí, documentalo","No por ahora","Sí y priorízalo"],'
                '"recommended_index":0}'
            )

    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *a, **k: _CaptureLLM(),
    )
    out = generate_followup_suggestions(
        object(),
        "chat-1",
        last_user_text="¿Sigue el bug?",
        last_assistant_text=(
            "El bug sigue activo.\n"
            "¿Quieres que documente esto como issue en el repo de Capadonna-Driller?"
        ),
    )
    assert out["suggestions"][0].startswith("Sí")
    assert len(captured) == 2
    human = str(getattr(captured[1], "content", ""))
    assert "PRIORIZA chips" in human
    assert "respondan esa pregunta" in human
    system = str(getattr(captured[0], "content", ""))
    assert "PRIORIDAD 1" in system


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
    _patch_triplet(monkeypatch)

    def _fail_if_called(*a, **k):
        raise AssertionError("build_llm no debería llamarse sin texto del asistente")

    monkeypatch.setattr("duckclaw.integrations.llm_providers.build_llm", _fail_if_called)
    out = generate_followup_suggestions(
        object(), "chat-1", last_user_text="hola", last_assistant_text="   "
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
