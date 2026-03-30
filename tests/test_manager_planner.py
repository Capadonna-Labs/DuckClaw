"""Tests del planner JSON del Manager (parse, truncado, sin red)."""

from __future__ import annotations

import pytest


def test_plan_task_bi_analyst_meta_capabilities() -> None:
    from duckclaw.graphs.manager_graph import _plan_task

    task, override = _plan_task("Que puedes hacer?", "BI-Analyst")
    assert override is None
    assert "analista de datos" in task.lower()
    assert "agente de investigación" in task.lower() or "investigación activa" in task.lower()

    # Otro worker: no debe aplicar la rama BI
    task2, _ = _plan_task("Que puedes hacer?", "finanz")
    assert task2 == "Que puedes hacer?"


def test_truncate_plan_title_words() -> None:
    from duckclaw.graphs.manager_graph import _truncate_plan_title_words

    assert _truncate_plan_title_words("") == ""
    assert _truncate_plan_title_words("  ") == ""
    assert _truncate_plan_title_words("Un solo") == "Un solo"
    assert _truncate_plan_title_words("one two three four five six seven") == "one two three four five"


def test_extract_json_object() -> None:
    from duckclaw.graphs.manager_graph import _extract_json_object

    assert _extract_json_object("") is None
    assert _extract_json_object("not json") is None
    d = _extract_json_object('{"plan_title": "Hola", "tasks": ["a"]}')
    assert d == {"plan_title": "Hola", "tasks": ["a"]}
    d2 = _extract_json_object('prefix {"plan_title": "X", "tasks": []} suffix')
    assert d2 == {"plan_title": "X", "tasks": []}


def test_coerce_planner_payload() -> None:
    from duckclaw.graphs.manager_graph import _coerce_planner_payload

    t, tasks = _coerce_planner_payload({"plan_title": "Título", "tasks": ["u1", "u2"]})
    assert t == "Título"
    assert tasks == ["u1", "u2"]
    t2, tasks2 = _coerce_planner_payload({"plan_title": "  x  ", "tasks": None})
    assert t2 == "x"
    assert tasks2 == []
    with pytest.raises(ValueError):
        _coerce_planner_payload([])
    with pytest.raises(ValueError):
        _coerce_planner_payload({"plan_title": "", "tasks": []})
    with pytest.raises(ValueError):
        _coerce_planner_payload({"plan_title": "ok", "tasks": "nope"})


def test_llm_plan_from_model_returns_none_on_bad_invoke() -> None:
    from duckclaw.graphs.manager_graph import _llm_plan_from_model

    class _Boom:
        def invoke(self, _messages):  # noqa: ANN001
            raise RuntimeError("no API")

    assert _llm_plan_from_model(_Boom(), "hola", "Eres un planner.") is None


def test_llm_plan_from_model_parses_response() -> None:
    from duckclaw.graphs.manager_graph import _llm_plan_from_model

    class _Ok:
        def invoke(self, _messages):  # noqa: ANN001
            class R:
                content = '{"plan_title":"Consulta catálogo ropa","tasks":["Listar productos","Responder precios"]}'

            return R()

    out = _llm_plan_from_model(_Ok(), "¿Qué tienes?", "Instrucciones.")
    assert out is not None
    title, tasks = out
    assert title == "Consulta catálogo ropa"
    assert len(title.split()) <= 5
    assert tasks == ["Listar productos", "Responder precios"]


def test_llm_plan_from_model_truncates_long_title() -> None:
    from duckclaw.graphs.manager_graph import _llm_plan_from_model

    class _Ok:
        def invoke(self, _messages):  # noqa: ANN001
            class R:
                content = (
                    '{"plan_title":"one two three four five six seven",'
                    '"tasks":["t"]}'
                )

            return R()

    out = _llm_plan_from_model(_Ok(), "x", "sys")
    assert out is not None
    assert out[0] == "one two three four five"


def test_manager_greeting_fast_path_ok() -> None:
    from duckclaw.graphs.manager_graph import _greeting_fast_reply_text, _manager_greeting_fast_path_ok

    assert _manager_greeting_fast_path_ok("Hola!")
    assert _manager_greeting_fast_path_ok("buenos días")
    assert not _manager_greeting_fast_path_ok("/help")
    assert not _manager_greeting_fast_path_ok("hola necesito ventas")
    assert "analyst" in _greeting_fast_reply_text("BI-Analyst").lower() or "bi" in _greeting_fast_reply_text(
        "BI-Analyst"
    ).lower()


def test_manager_capabilities_fast_path_ok() -> None:
    from duckclaw.graphs.manager_graph import (
        _capabilities_fast_reply_text,
        _manager_capabilities_fast_path_ok,
        _manager_greeting_fast_path_ok,
    )

    assert _manager_capabilities_fast_path_ok("Que puedes hacer?")
    assert _manager_capabilities_fast_path_ok("¿En qué puedes ayudarme?")
    assert _manager_capabilities_fast_path_ok("what can you do")
    assert not _manager_capabilities_fast_path_ok("hola")
    assert not _manager_capabilities_fast_path_ok("/help")
    assert not _manager_capabilities_fast_path_ok("que puedes hacer con la tabla ventas")
    assert _manager_capabilities_fast_path_ok("Dame un ejemplo de algo que puedas hacer")
    assert _manager_capabilities_fast_path_ok("Dame un ejemplo de algo que puedes hacer")
    assert _manager_capabilities_fast_path_ok("Muéstrame un ejemplo")
    assert not _manager_capabilities_fast_path_ok("dame un ejemplo de ventas por región")
    assert _manager_greeting_fast_path_ok("hola")
    assert "duckdb" in _capabilities_fast_reply_text("BI-Analyst").lower()
    assert "ejemplo" in _capabilities_fast_reply_text("BI-Analyst").lower()
