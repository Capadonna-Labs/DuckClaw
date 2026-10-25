"""run_sandbox: alias command/script → code y rechazo de dumps de mensajes."""

from __future__ import annotations

import json

from duckclaw.graphs.sandbox import RunSandboxArgs, sandbox_tool_factory


def test_run_sandbox_args_coerces_command_alias() -> None:
    args = RunSandboxArgs.model_validate({"command": "print(1)", "language": "python"})
    assert args.resolved_code() == "print(1)"


def test_run_sandbox_args_prefers_explicit_code() -> None:
    args = RunSandboxArgs.model_validate({"code": "print(2)", "command": "print(9)"})
    assert args.resolved_code() == "print(2)"


def test_run_sandbox_tool_accepts_command_without_docker(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_run_in_sandbox(**kwargs):  # noqa: ANN003
        calls.append(kwargs)

        class _R:
            exit_code = 0
            stdout = "ok"
            stderr = ""
            timed_out = False
            attempts = 1
            sandbox_run_id = None
            artifact_ids = []
            artifacts = []

        return _R()

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", _fake_run_in_sandbox)
    tool = sandbox_tool_factory(db=None, llm=None)
    out = json.loads(tool.invoke({"command": "print('hi')", "language": "python"}))
    assert out["exit_code"] == 0
    assert calls and calls[0]["code"] == "print('hi')"


def test_run_sandbox_tool_rejects_message_dump_without_docker(monkeypatch) -> None:
    def _boom(**kwargs):  # noqa: ANN003
        raise AssertionError("run_in_sandbox must not be called for message dumps")

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", _boom)
    tool = sandbox_tool_factory(db=None, llm=None)
    dump = "content='' additional_kwargs={'refusal': None} response_metadata={}"
    out = json.loads(tool.invoke({"code": dump}))
    assert out["exit_code"] == 1
    assert "dump de mensaje" in out["output"].lower() or "AIMessage" in out["output"]


def test_run_sandbox_tool_missing_code_is_fast_error(monkeypatch) -> None:
    def _boom(**kwargs):  # noqa: ANN003
        raise AssertionError("run_in_sandbox must not be called without code")

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", _boom)
    tool = sandbox_tool_factory(db=None, llm=None)
    out = json.loads(tool.invoke({"language": "python"}))
    assert out["exit_code"] == 1
    assert "code" in out["output"].lower()


def test_run_sandbox_llm_schema_requires_code_and_hides_runtime_args() -> None:
    """2026-10-24: deepseek sent {"chat_id": "quant_analyst"} 40+ times — schema had no required
    field and exposed runtime-only chat_id/worker_id."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    params = convert_to_openai_tool(sandbox_tool_factory(db=None, llm=None))["function"]["parameters"]
    assert "code" in (params.get("required") or [])
    assert "chat_id" not in params["properties"]
    assert "worker_id" not in params["properties"]
    assert "data_sql" in params["properties"]


def test_run_sandbox_only_runtime_args_is_clear_error(monkeypatch) -> None:
    def _boom(**kwargs):  # noqa: ANN003
        raise AssertionError("run_in_sandbox must not be called without code")

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", _boom)
    tool = sandbox_tool_factory(db=None, llm=None)
    out = json.loads(tool.invoke({"chat_id": "quant_analyst", "worker_id": "quant_analyst"}))
    assert out["exit_code"] == 1
    assert out["error_code"] == "missing_code"
    assert "obligatorio 'code'" in out["output"]
    assert "data_sql" in out["output"]


def test_run_sandbox_runtime_args_still_reach_the_tool(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake(**kwargs):  # noqa: ANN003
        calls.append(kwargs)

        class _R:
            exit_code = 0
            stdout = "2"
            stderr = ""
            timed_out = False
            attempts = 1
            sandbox_run_id = None
            artifact_ids = []
            artifacts = []

        return _R()

    monkeypatch.setattr("duckclaw.graphs.sandbox.run_in_sandbox", _fake)
    tool = sandbox_tool_factory(db=None, llm=None)
    for args in ({"code": "print(1+1)"}, {"source": "print(1+1)"}, {"script": "print(1+1)"}):
        out = json.loads(tool.invoke({**args, "chat_id": "admin-conv-x", "worker_id": "quant_analyst"}))
        assert out["exit_code"] == 0
    assert all(c["code"] == "print(1+1)" for c in calls)
    assert all(c["chat_id"] == "admin-conv-x" and c["worker_id"] == "quant_analyst" for c in calls)
