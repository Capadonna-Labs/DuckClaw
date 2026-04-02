"""Tests para el fly command /sandbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.graphs.on_the_fly_commands import (
    execute_sandbox_toggle,
    get_chat_state,
    handle_command,
    set_chat_state,
)
from duckclaw import DuckClaw
from duckclaw.workers.factory import build_worker_graph, filter_tools_for_sandbox


@pytest.fixture
def db(tmp_path):
    """Real DuckDB en archivo temporal (evita lock del DB en ejecución PM2)."""
    path = str(tmp_path / "finanz_test_worker_sandbox.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return DuckClaw(path)


def test_sandbox_toggle_persists_off(db) -> None:
    chat_id = "test_sandbox_001"
    set_chat_state(db, chat_id, "sandbox_enabled", "")

    reply = execute_sandbox_toggle(db, chat_id, "false")
    assert "desactivado" in reply.lower()
    assert get_chat_state(db, chat_id, "sandbox_enabled") == "false"


def test_sandbox_toggle_persists_on(db) -> None:
    chat_id = "test_sandbox_002"
    set_chat_state(db, chat_id, "sandbox_enabled", "false")

    reply = execute_sandbox_toggle(db, chat_id, "true")
    assert "habilitado" in reply.lower()
    assert get_chat_state(db, chat_id, "sandbox_enabled") == "true"


def test_handle_command_processes_sandbox(db) -> None:
    chat_id = "test_sandbox_003"
    set_chat_state(db, chat_id, "sandbox_enabled", "true")

    reply = handle_command(db, chat_id, "/sandbox off")
    assert reply is not None
    assert "desactivado" in reply.lower()
    assert get_chat_state(db, chat_id, "sandbox_enabled") == "false"


def test_filter_tools_for_sandbox_removes_run_sandbox() -> None:
    class DummyTool:
        def __init__(self, name: str) -> None:
            self.name = name

    tools = [DummyTool("run_sandbox"), DummyTool("read_sql"), DummyTool("inspect_schema")]

    tools_off = filter_tools_for_sandbox(tools, enabled=False)
    assert [t.name for t in tools_off] == ["read_sql", "inspect_schema"]

    tools_on = filter_tools_for_sandbox(tools, enabled=True)
    assert [t.name for t in tools_on] == ["run_sandbox", "read_sql", "inspect_schema"]


def test_worker_sandbox_binding_respects_chat_id(tmp_path) -> None:
    """
    Smoke test unitario:
    - Si sandbox_enabled=true para chat_id=X, el worker debe "usar modo ON".
    - Si sandbox_enabled=false para chat_id=Y, el worker debe "usar modo OFF".

    No ejecuta Docker; valida selección de LLM por estado (vía tool binding).
    """

    from langchain_core.messages import AIMessage

    class _StubBoundLLM:
        def __init__(self, tool_names: list[str]) -> None:
            self._tool_names = tool_names

        def invoke(self, _messages: list[Any]) -> AIMessage:
            enabled = "run_sandbox" in self._tool_names
            return AIMessage(content="SANDBOX_ON" if enabled else "SANDBOX_OFF")

    class _StubLLM:
        def bind_tools(self, tools: list[Any], **_kwargs: Any) -> _StubBoundLLM:
            tool_names = [getattr(t, "name", "") for t in tools]
            tool_names = [n for n in tool_names if n]
            return _StubBoundLLM(tool_names)

    db_path = str(tmp_path / "finanz_test_worker_sandbox.duckdb")
    db = DuckClaw(db_path)
    chat_on = "test_worker_sandbox_on"
    chat_off = "test_worker_sandbox_off"
    set_chat_state(db, chat_on, "sandbox_enabled", "true")
    set_chat_state(db, chat_off, "sandbox_enabled", "false")

    worker_graph = build_worker_graph("finanz", db_path, _StubLLM(), reuse_db=db)

    res_on = worker_graph.invoke(
        {"incoming": "Ejecuta el código: print(2+2)", "history": [], "chat_id": chat_on}
    )
    assert res_on.get("reply", "").strip() == "SANDBOX_ON"

    res_off = worker_graph.invoke(
        {"incoming": "Ejecuta el código: print(2+2)", "history": [], "chat_id": chat_off}
    )
    assert res_off.get("reply", "").strip() == "SANDBOX_OFF"


def test_worker_sandbox_tool_call_uses_chat_id(tmp_path, monkeypatch) -> None:
    """
    Reproduce el bug observado en logs:
    - Primero el agent genera tool_call: `run_sandbox`
    - Luego el tools_node debe consultar sandbox_enabled con el chat_id correcto.
    """

    from langchain_core.messages import AIMessage, ToolMessage
    from duckclaw.graphs import sandbox as sandbox_mod
    from duckclaw.graphs.sandbox import ExecutionResult

    def _fake_run_in_sandbox(**_kwargs: Any) -> ExecutionResult:
        return ExecutionResult(exit_code=0, stdout="OK", stderr="", timed_out=False, artifacts=[], attempts=1)

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fake_run_in_sandbox)

    class _StubBoundLLM:
        def __init__(self, tool_names: list[str]) -> None:
            self._tool_names = tool_names

        def invoke(self, messages: list[Any]) -> AIMessage:
            last = messages[-1] if messages else None
            if isinstance(last, ToolMessage):
                # Devolver el contenido exacto del tool para que set_reply lo propague.
                return AIMessage(content=f"RESULT:{last.content}")
            if "run_sandbox" in self._tool_names:
                return AIMessage(
                    content="CALL",
                    tool_calls=[
                        {
                            "name": "run_sandbox",
                            "id": "1",
                            "args": {
                                "code": "print(2+2)",
                                "language": "python",
                                "data_sql": "",
                                "session_id": "s1",
                                "worker_id": "finanz",
                            },
                        }
                    ],
                )
            return AIMessage(content="NO_SANDBOX", tool_calls=[])

    class _StubLLM:
        def bind_tools(self, tools: list[Any], **_kwargs: Any) -> _StubBoundLLM:
            tool_names = [getattr(t, "name", "") for t in tools]
            tool_names = [n for n in tool_names if n]
            return _StubBoundLLM(tool_names)

    db_path = str(tmp_path / "finanz_test_worker_sandbox_tool_call.duckdb")
    db = DuckClaw(db_path)

    chat_on = "test_worker_sandbox_tool_on"
    chat_off = "test_worker_sandbox_tool_off"
    set_chat_state(db, chat_on, "sandbox_enabled", "true")
    set_chat_state(db, chat_off, "sandbox_enabled", "false")

    worker_graph = build_worker_graph("finanz", db_path, _StubLLM(), reuse_db=db)

    res_on = worker_graph.invoke(
        {"incoming": "Ejecuta el código: print(2+2)", "history": [], "chat_id": chat_on}
    )
    assert "exit_code" in res_on.get("reply", "")
    assert "Sandbox deshabilitado" not in res_on.get("reply", "")

    res_off = worker_graph.invoke(
        {"incoming": "Ejecuta el código: print(2+2)", "history": [], "chat_id": chat_off}
    )
    assert "Sandbox deshabilitado" in res_off.get("reply", "") or "NO_SANDBOX" in res_off.get("reply", "")

