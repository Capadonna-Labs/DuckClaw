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
