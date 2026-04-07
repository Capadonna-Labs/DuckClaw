"""Tests del planner JSON del Manager (parse, truncado, sin red)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_plan_task_job_hunter_uses_tavily_not_run_sandbox_only() -> None:
    from duckclaw.graphs.manager_graph import _plan_task

    task, override = _plan_task(
        "busca un trabajo de data scientist en Colombia y pásame la url",
        "Job-Hunter",
    )
    assert override is None
    assert "tavily_search" in task.lower()
    assert "run_browser_sandbox" in task.lower()
    assert "income_injection" in task.lower()
    assert "3 vacantes" in task.lower() or "hasta 3" in task.lower()
    # Otro worker: no debe aplicar la rama Job-Hunter
    task2, _ = _plan_task(
        "busca un trabajo de data scientist en Colombia y pásame la url",
        "finanz",
    )
    assert task2 == "busca un trabajo de data scientist en Colombia y pásame la url"


def test_cashflow_stress_intent_detection() -> None:
    from duckclaw.graphs.manager_graph import _user_signals_cashflow_stress

    assert _user_signals_cashflow_stress("ando ilíquido y no me alcanza este mes")
    assert _user_signals_cashflow_stress("necesito ingresos extra para pagar deudas")
    assert not _user_signals_cashflow_stress("muéstrame el esquema de tablas")


def test_strip_leading_subagent_instance_headers() -> None:
    from duckclaw.graphs.manager_graph import (
        _prepend_subagent_label_once,
        _strip_leading_subagent_instance_headers,
    )

    raw = "finanz 2\n\nfinanz 4\n\nfinanz 1\n\nHola cuerpo"
    assert _strip_leading_subagent_instance_headers(raw) == "Hola cuerpo"
    single = _prepend_subagent_label_once(raw, "finanz 3")
    assert single.startswith("finanz 3\n\n")
    assert "finanz 2" not in single
    assert "Hola cuerpo" in single


def test_lc_messages_to_chatml_strips_repeated_subagent_headers() -> None:
    from langchain_core.messages import AIMessage

    from duckclaw.graphs.conversation_traces import _lc_messages_to_chatml

    m = AIMessage(content="finanz 2\n\nfinanz 4\n\nHola cuerpo")
    out = _lc_messages_to_chatml([m])
    assert len(out) == 1
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "Hola cuerpo"


def test_pick_job_hunter_worker_from_team() -> None:
    from duckclaw.graphs.manager_graph import _pick_job_hunter_worker

    assert _pick_job_hunter_worker(["finanz", "Job-Hunter"]) == "Job-Hunter"
    assert _pick_job_hunter_worker(["finanz", "job_hunter"]) == "job_hunter"
    assert _pick_job_hunter_worker(["finanz", "bi-analyst"]) is None


def test_detect_income_injection_marker() -> None:
    from duckclaw.graphs.manager_graph import _contains_income_injection_request

    assert _contains_income_injection_request("rechazo por déficit [A2A_REQUEST: INCOME_INJECTION]")
    assert _contains_income_injection_request("... [a2a_request: income_injection] ...")
    assert not _contains_income_injection_request("sin marcador de handoff")


def test_detect_job_opportunity_tracking_marker() -> None:
    from duckclaw.graphs.manager_graph import _contains_job_opportunity_tracking_request

    assert _contains_job_opportunity_tracking_request("registro [a2a_request: job_opportunity_tracking]")
    assert not _contains_job_opportunity_tracking_request("solo income [a2a_request: income_injection]")


def test_plan_task_job_hunter_job_tracking_skips_tavily_mission() -> None:
    from duckclaw.graphs.manager_graph import _plan_task

    task, override = _plan_task(
        "TAREA: Misión A2A JOB_OPPORTUNITY_TRACKING.\nhttps://ejemplo.com/oferta",
        "Job-Hunter",
    )
    assert override is None
    assert "JOB_OPPORTUNITY_TRACKING" in task
    assert "uses tavily_search ni run_browser_sandbox salvo" in task.lower()
    assert "admin_sql" in task.lower() or "read_sql" in task.lower()


def test_plan_task_job_hunter_application_tracking_read_sql_no_tavily() -> None:
    from duckclaw.graphs.manager_graph import _plan_task, job_hunter_user_requests_job_search

    q = "dame el seguimiento de las vacantes a las que he aplicado"
    assert not job_hunter_user_requests_job_search(q)
    task, override = _plan_task(q, "Job-Hunter")
    assert override is None
    assert "job_opportunities" in task.lower()
    assert "read_sql" in task.lower()
    assert "prohibido" in task.lower() and "tavily_search" in task.lower()


def test_job_hunter_synthesis_task_does_not_trigger_tavily_intent() -> None:
    from duckclaw.graphs.manager_graph import job_hunter_user_requests_job_search

    syn = (
        "TAREA: JobHunter completó la misión INCOME_INJECTION. Sintetiza los resultados crudos "
        "prioriza 3 vacantes accionables"
    )
    assert not job_hunter_user_requests_job_search(syn)


def test_plan_task_summarize_directives_passthrough_despite_db_keywords_in_body() -> None:
    """El cuerpo inyectado puede decir 'estructura', 'schema', 'DuckDB', etc.; no debe convertirse en TAREA de tablas."""
    from duckclaw.graphs.manager_graph import _llm_plan, _plan_task

    stored = (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]\n"
        "- Cookbooks con estructura jerárquica y Postgres endpoint sobre DuckDB.\n"
        "- Ver tablas en information_schema si hace falta.\n\n"
        "Este bloque se obtuvo leyendo main.semantic_memory. Sintetiza."
    )
    task, override = _plan_task(stored, "Job-Hunter")
    assert override is None
    assert task == stored
    assert "TAREA: El usuario quiere ver las tablas" not in task

    title, tasks = _llm_plan(stored)
    assert title == "Síntesis de contexto almacenado"
    assert any("no listar tablas" in t.lower() for t in tasks)

    new_ctx = (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\n"
        "- Pipeline con esquema de datos y listar tablas en el dashboard.\n\n"
        "Sintetiza."
    )
    task2, _ = _plan_task(new_ctx, "Job-Hunter")
    assert task2 == new_ctx
    assert "SHOW TABLES" not in task2


def test_plan_task_summarize_stored_with_bom_still_passthrough() -> None:
    from duckclaw.graphs.manager_graph import _plan_task

    body = (
        "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]\n--- registro 1 ---\nx\n"
        "Este bloque se obtuvo leyendo main.semantic_memory."
    )
    task, override = _plan_task("\ufeff" + body, "Job-Hunter")
    assert override is None
    assert task == body
    assert "TAREA: El usuario quiere ver las tablas" not in task


def test_plan_task_context_add_vlm_passthrough_not_get_db_path() -> None:
    """/context --add + VLM: el cuerpo menciona símbolos/datos; no debe disparar TAREA get_db_path."""
    from duckclaw.graphs.manager_graph import _plan_task

    incoming = (
        "Usuario dice: /context --add\n"
        "Contexto visual adjunto: SPY, VIX; datos de precios y nombres de activos.\n"
        "[VLM_CONTEXT image_hash=ab confidence=0.74]"
    )
    task, override = _plan_task(incoming, "finanz")
    assert override is None
    assert task == incoming
    assert "get_db_path" not in task.lower()


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
    assert "osint" in _greeting_fast_reply_text("Job‐Hunter").lower()


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
    jh = _capabilities_fast_reply_text("Job-Hunter").lower()
    assert "osint" in jh and "discovery" in jh
    assert "osint" in _capabilities_fast_reply_text("job_hunter").lower()
    assert "osint" in _capabilities_fast_reply_text("Job‐Hunter").lower()  # U+2010 hyphen
    fz = _capabilities_fast_reply_text("finanz").lower()
    assert "ibkr" in fz and "duckdb" in fz
    assert "resumen" in fz or "cuenta" in fz


def test_manager_a2a_marker_routes_finanz_to_jobhunter_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs.manager_graph import build_manager_graph

    monkeypatch.delenv("DUCKCLAW_DEFAULT_WORKER_ID", raising=False)

    class _FakeDB:
        pass

    call_log: list[tuple[str, str, bool]] = []

    class _FakeWorkerGraph:
        def __init__(self, wid: str):
            self.wid = wid

        def invoke(self, worker_state, _config=None):  # noqa: ANN001
            task = str(worker_state.get("input") or "")
            suppressed = bool(worker_state.get("suppress_subagent_egress"))
            call_log.append((self.wid, task, suppressed))
            if re.sub(r"[^a-z0-9]", "", self.wid.lower()) == "jobhunter":
                # Simula sub-rutina intermedia: salida interna para síntesis, sin egress público.
                if suppressed:
                    return {"reply": "", "internal_reply": '{"quick_hits":[{"role":"Data Engineer"}]}'}
                return {"reply": "jobhunter public"}
            if self.wid.lower() == "finanz":
                if "JobHunter completó la misión INCOME_INJECTION" in task:
                    return {"reply": "Reporte final sintetizado por Finanz."}
                return {"reply": "Operación rechazada por déficit. [A2A_REQUEST: INCOME_INJECTION]"}
            return {"reply": "ok"}

    def _fake_builder(worker_id, *_args, **_kwargs):  # noqa: ANN001
        return _FakeWorkerGraph(str(worker_id))

    monkeypatch.setattr("duckclaw.workers.factory.build_worker_graph", _fake_builder)
    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda *_a, **_k: ["finanz", "Job-Hunter"])
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.get_effective_team_templates",
        lambda *_a, **_k: ["finanz", "Job-Hunter"],
    )
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.get_chat_state", lambda *_a, **_k: "off")
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.append_task_audit", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.activity.set_busy", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.activity.set_idle", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.chat_heartbeat.schedule_chat_heartbeat_dm", lambda *_a, **_k: None)

    import duckclaw.graphs.manager_graph as _mgr_mod

    _mgr_mod._worker_graph_cache.clear()
    graph = build_manager_graph(_FakeDB(), llm=None)
    out = graph.invoke(
        {
            "incoming": "Quiero invertir 5M COP hoy mismo.",
            "input": "Quiero invertir 5M COP hoy mismo.",
            "chat_id": "test-chat",
            "tenant_id": "default",
            "user_id": "u1",
            "available_templates": ["finanz", "Job-Hunter"],
        }
    )

    # Flujo esperado: Finanz -> JobHunter (silenciado) -> Finanz síntesis.
    assert len(call_log) >= 3
    assert call_log[0][0] == "finanz"
    assert re.sub(r"[^a-z0-9]", "", call_log[1][0].lower()) == "jobhunter"
    assert call_log[1][2] is True
    assert call_log[2][0] == "finanz"
    assert "Reporte final sintetizado" in str(out.get("reply") or "")


def test_manager_job_track_marker_routes_finanz_to_jobhunter_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """A2A JOB_OPPORTUNITY_TRACKING: Finanz emite marcador → JobHunter persiste → Finanz confirma."""
    from duckclaw.graphs.manager_graph import build_manager_graph

    monkeypatch.delenv("DUCKCLAW_DEFAULT_WORKER_ID", raising=False)

    class _FakeDB:
        pass

    call_log: list[tuple[str, str, bool]] = []

    class _FakeWorkerGraph:
        def __init__(self, wid: str):
            self.wid = wid

        def invoke(self, worker_state, _config=None):  # noqa: ANN001
            task = str(worker_state.get("input") or "")
            suppressed = bool(worker_state.get("suppress_subagent_egress"))
            call_log.append((self.wid, task, suppressed))
            if re.sub(r"[^a-z0-9]", "", self.wid.lower()) == "jobhunter":
                if suppressed:
                    return {"reply": "", "internal_reply": '{"rows":1}'}
                assert "JOB_OPPORTUNITY_TRACKING" in task
                return {"reply": "INSERT job_opportunities OK"}
            if self.wid.lower() == "finanz":
                if "JobHunter persistió datos" in task or "job_opportunities" in task.lower():
                    return {"reply": "Vacante registrada en CRM."}
                return {"reply": "Delegando registro. [a2a_request: job_opportunity_tracking]"}
            return {"reply": "ok"}

    def _fake_builder(worker_id, *_args, **_kwargs):  # noqa: ANN001
        return _FakeWorkerGraph(str(worker_id))

    monkeypatch.setattr("duckclaw.workers.factory.build_worker_graph", _fake_builder)
    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda *_a, **_k: ["finanz", "Job-Hunter"])
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.get_effective_team_templates",
        lambda *_a, **_k: ["finanz", "Job-Hunter"],
    )
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.get_chat_state", lambda *_a, **_k: "off")
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.append_task_audit", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.activity.set_busy", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.activity.set_idle", lambda *_a, **_k: None)
    monkeypatch.setattr("duckclaw.graphs.chat_heartbeat.schedule_chat_heartbeat_dm", lambda *_a, **_k: None)

    import duckclaw.graphs.manager_graph as _mgr_mod

    _mgr_mod._worker_graph_cache.clear()
    graph = build_manager_graph(_FakeDB(), llm=None)
    # Evitar palabras URL tipo «oferta» + http que dispararían plan → JobHunter antes que Finanz.
    out = graph.invoke(
        {
            "incoming": "Registra mi postulación https://ejemplo.com/job/abc",
            "input": "Registra mi postulación https://ejemplo.com/job/abc",
            "chat_id": "test-chat-jt",
            "tenant_id": "default",
            "user_id": "u1",
            "available_templates": ["finanz", "Job-Hunter"],
        }
    )

    assert len(call_log) >= 3
    assert call_log[0][0] == "finanz"
    assert re.sub(r"[^a-z0-9]", "", call_log[1][0].lower()) == "jobhunter"
    assert "JOB_OPPORTUNITY_TRACKING" in call_log[1][1]
    assert call_log[2][0] == "finanz"
    assert "Vacante registrada" in str(out.get("reply") or "")


def test_finanz_manifest_includes_job_opportunities_allowlist() -> None:
    raw = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / "finanz"
        / "manifest.yaml"
    ).read_text(encoding="utf-8")
    assert "job_opportunities" in raw
    assert "allowed_tables:" in raw


def test_worker_tool_names_from_messages_embedded_json_in_content() -> None:
    """MLX sin tool_calls: el nombre de tool se infiere del JSON en content del último AIMessage."""
    from langchain_core.messages import AIMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    ai = AIMessage(
        content='{"name": "read_sql", "parameters": {"query": "SELECT 1"}}',
    )
    assert _worker_tool_names_from_messages([ai]) == ["read_sql"]


def test_worker_tool_names_from_messages_dict_assistant_embedded_json() -> None:
    """Estado serializado como dict ChatML (último assistant con JSON de tool)."""
    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    msgs = [{"role": "assistant", "content": '{"name": "read_sql", "parameters": {"query": "SELECT 1"}}'}]
    assert _worker_tool_names_from_messages(msgs) == ["read_sql"]


def test_worker_tool_names_from_messages_tuple_same_as_list() -> None:
    """LangGraph puede devolver messages como tupla; el manager debe inferir tools igual que con lista."""
    from langchain_core.messages import AIMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    ai = AIMessage(
        content='{"name": "read_sql", "parameters": {"query": "SELECT 1"}}',
    )
    assert _worker_tool_names_from_messages((ai,)) == ["read_sql"]


def test_worker_tool_names_from_messages_embedded_earlier_ai_same_turn() -> None:
    """Mismo turno: varios AIMessage; el JSON de tool puede ir en uno anterior al último assistant."""
    from langchain_core.messages import AIMessage, HumanMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    ai_tool = AIMessage(
        content='{"name": "read_sql", "parameters": {"query": "SELECT 1"}}',
    )
    ai_text = AIMessage(content="Aquí tienes el resultado.")
    msgs = [HumanMessage(content="Dame cuentas"), ai_tool, ai_text]
    assert _worker_tool_names_from_messages(msgs) == ["read_sql"]


def test_worker_tool_names_additional_kwargs_tool_calls() -> None:
    """MLX / OpenAI-compat a veces dejan tool_calls solo en additional_kwargs."""
    from langchain_core.messages import HumanMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    class _AI:
        type = "ai"
        tool_calls: list = []
        content = ""
        additional_kwargs = {
            "tool_calls": [{"type": "function", "function": {"name": "read_sql", "arguments": "{}"}}]
        }

    msgs = [HumanMessage(content="q"), _AI()]
    assert _worker_tool_names_from_messages(msgs) == ["read_sql"]


def test_worker_tool_names_read_sql_regex_fallback() -> None:
    """JSON roto en content: aún detectamos read_sql para logs del manager."""
    from langchain_core.messages import AIMessage, HumanMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    ai = AIMessage(
        content='x {"name": "read_sql", "parameters": {"query": "SELECT 1" no cierra',
    )
    msgs = [HumanMessage(content="x"), ai]
    assert "read_sql" in _worker_tool_names_from_messages(msgs)


def test_worker_tool_names_from_messages_embedded_json_after_prefix() -> None:
    """MLX a veces antepone texto antes del objeto JSON de la tool."""
    from langchain_core.messages import AIMessage, HumanMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    ai = AIMessage(
        content='Consulto la base.\n{"name": "read_sql", "parameters": {"query": "SELECT 1"}}',
    )
    msgs = [HumanMessage(content="q"), ai]
    assert _worker_tool_names_from_messages(msgs) == ["read_sql"]


def test_worker_tool_names_from_messages_dict_and_object_tool_calls() -> None:
    from types import SimpleNamespace

    from langchain_core.messages import AIMessage, ToolMessage

    from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

    class _FakeMsg:
        __slots__ = ("tool_calls",)

        def __init__(self, tool_calls: list) -> None:
            self.tool_calls = tool_calls

    ai_lc = AIMessage(content="", tool_calls=[{"name": "read_sql", "id": "1", "args": {}}])
    fake_obj_tc = _FakeMsg(tool_calls=[SimpleNamespace(name="tavily_search")])
    tm = ToolMessage(content="ok", tool_call_id="1", name="read_sql")
    names = _worker_tool_names_from_messages([ai_lc, fake_obj_tc, tm])
    # AIMessage normaliza tool_calls a objetos; dedupe mantiene un solo read_sql.
    assert "read_sql" in names and "tavily_search" in names
    assert names.index("read_sql") < names.index("tavily_search")
