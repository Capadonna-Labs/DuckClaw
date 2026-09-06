"""Tests for worker-to-worker allowed_delegates invoke."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.workers.manifest import WorkerSpec, _parse_allowed_delegates, build_spec_from_manifest


def test_manifest_parses_allowed_delegates() -> None:
    data = {
        "id": "worker_a",
        "skills": [],
        "allowed_delegates": ["worker_b", "worker-b"],
    }
    spec = build_spec_from_manifest(data, "worker_a", Path("/tmp/w"))
    assert "worker_b" in spec.allowed_delegates
    assert len(spec.allowed_delegates) == 1


def test_parse_allowed_delegates_empty() -> None:
    assert _parse_allowed_delegates({}) == ()
    assert _parse_allowed_delegates({"allowed_delegates": "a, b"}) == ("a", "b")


def test_invoke_delegated_worker_rejects_not_in_allowlist() -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker

    caller_spec = WorkerSpec(
        worker_id="worker_a",
        logical_worker_id="worker_a",
        name="wa",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.1,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=True,
        worker_dir=Path("/tmp"),
        allowed_delegates=("worker_b",),
    )
    result = invoke_delegated_worker(
        caller_worker_id="worker_a",
        caller_spec=caller_spec,
        target_worker_id="other_worker",
        task="build dashboard",
        state={"chat_id": "chat-1", "tenant_id": "default"},
        db=MagicMock(),
        llm=None,
        templates_root=None,
        tenant_id="default",
    )
    assert result.status == "error"
    assert result.error == "not_allowed"


def test_invoke_delegated_worker_rejects_nested_depth() -> None:
    from duckclaw.workers import worker_invoke as wi

    caller_spec = SimpleNamespace(allowed_delegates=("worker_b",))
    wi._delegate_depth.set(1)
    try:
        result = wi.invoke_delegated_worker(
            caller_worker_id="worker_a",
            caller_spec=caller_spec,
            target_worker_id="worker_b",
            task="nested",
            state={"chat_id": "chat-1"},
            db=MagicMock(),
            llm=None,
            templates_root=None,
            tenant_id="default",
        )
    finally:
        wi._delegate_depth.set(0)
    assert result.status == "error"
    assert result.error == "depth_exceeded"


def test_vault_invoke_lock_is_reentrant_for_delegation() -> None:
    from duckclaw.manager.manager_worker_cache import get_vault_invoke_lock

    path = "/tmp/duckclaw-delegate-vault-test.duckdb"
    lock = get_vault_invoke_lock(path)
    assert lock is not None
    lock.acquire()
    try:
        nested = get_vault_invoke_lock(path)
        assert nested is lock
        nested.acquire()
        nested.release()
    finally:
        lock.release()


def test_invoke_delegated_worker_no_deadlock_when_delegate_shares_vault(monkeypatch) -> None:
    """Regression for the cross-thread vault-lock deadlock: a worker delegating to another
    worker that resolves to the same vault used to hang because invoke_worker_graph's
    ThreadPoolExecutor thread couldn't see the ancestor's RLock via contextvars, so it tried to
    re-acquire a lock owned by a different (blocked) thread. A short timeout turns a regression
    into a fast failure instead of a hang."""
    from duckclaw.manager.manager_worker_cache import get_vault_invoke_lock
    from duckclaw.workers import worker_invoke as wi

    monkeypatch.setattr(wi, "_DELEGATE_INVOKE_TIMEOUT_SEC", 3.0)

    vault_path = "/tmp/duckclaw-same-vault-delegate-test.duckdb"
    parent_lock = get_vault_invoke_lock(vault_path)

    delegate_graph = MagicMock()
    delegate_graph.invoke.return_value = {"reply": "dashboard listo", "messages": []}
    caller_spec = SimpleNamespace(allowed_delegates=("worker_b",))

    def run_caller_turn(*_args: object, **_kwargs: object) -> dict:
        with patch(
            "duckclaw.workers.manifest.load_manifest",
            return_value=SimpleNamespace(forge_vault_binding=None),
        ):
            with patch("duckclaw.workers.factory.build_worker_graph", return_value=delegate_graph):
                with patch("duckclaw.workers.factory._get_db_path", return_value=vault_path):
                    result = wi.invoke_delegated_worker(
                        caller_worker_id="worker_a",
                        caller_spec=caller_spec,
                        target_worker_id="worker_b",
                        task="publicar dashboard HTML",
                        state={"chat_id": "chat-1", "tenant_id": "default"},
                        db=MagicMock(),
                        llm=MagicMock(),
                        templates_root=None,
                        tenant_id="default",
                        vault_db_path=vault_path,
                    )
        return {"reply": result.reply, "messages": [], "_result": result}

    caller_graph = SimpleNamespace(invoke=run_caller_turn)

    # Mirrors manager_nodes_invoke.py: acquire the per-vault lock for the whole caller turn,
    # publish it as the parent lock, then run the caller's graph through invoke_worker_graph.
    parent_lock.acquire()
    wi.set_parent_vault_invoke_lock(parent_lock)
    try:
        outcome = wi.invoke_worker_graph(caller_graph, {}, chat_id="chat-1", timeout_sec=3.0)
    finally:
        wi.set_parent_vault_invoke_lock(None)
        parent_lock.release()

    assert outcome["_result"].status == "success"


def test_invoke_delegated_worker_injects_report_id_from_chat() -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker

    caller_spec = SimpleNamespace(allowed_delegates=("worker_b",))
    captured_task: list[str] = []

    def fake_prepare(*, incoming: str, **kwargs: object) -> dict:
        captured_task.append(incoming)
        return {"messages": []}

    with patch("duckclaw.workers.manifest.load_manifest", return_value=SimpleNamespace(forge_vault_binding=None)):
        with patch("duckclaw.workers.factory.build_worker_graph") as mock_build:
            graph = MagicMock()
            graph.invoke.return_value = {"reply": "ok", "messages": []}
            mock_build.return_value = graph
            with patch(
                "duckclaw.manager.manager_invoke_helpers.prepare_worker_invoke_state",
                side_effect=fake_prepare,
            ):
                invoke_delegated_worker(
                    caller_worker_id="worker_a",
                    caller_spec=caller_spec,
                    target_worker_id="worker_b",
                    task="publicar dashboard HTML",
                    state={"chat_id": "admin-conv-abc", "tenant_id": "default"},
                    db=MagicMock(),
                    llm=MagicMock(),
                    templates_root=None,
                    tenant_id="default",
                )
    assert captured_task
    assert captured_task[0].startswith("report_id=admin-conv-abc")


@patch("duckclaw.workers.factory.build_worker_graph")
def test_invoke_delegated_worker_uses_graph_cache(mock_build_graph: MagicMock) -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker

    cached = MagicMock()
    cached.invoke.return_value = {"reply": "cached", "messages": []}

    caller_spec = SimpleNamespace(allowed_delegates=("worker_b",))
    with patch("duckclaw.workers.manifest.load_manifest", return_value=SimpleNamespace(forge_vault_binding=None)):
        with patch(
            "duckclaw.manager.manager_worker_cache.worker_graph_cache_get",
            return_value=cached,
        ) as cache_get:
            with patch(
                "duckclaw.manager.manager_worker_cache.remember_worker_graph_cache",
            ) as cache_put:
                result = invoke_delegated_worker(
                    caller_worker_id="worker_a",
                    caller_spec=caller_spec,
                    target_worker_id="worker_b",
                    task="report_id=chat-abc publish html dashboard",
                    state={"chat_id": "chat-abc", "tenant_id": "default", "user_id": "u1"},
                    db=MagicMock(_path="/tmp/hub.duckdb", _read_only=True),
                    llm=MagicMock(),
                    templates_root=None,
                    tenant_id="default",
                    vault_db_path="/tmp/worker-a-vault.duckdb",
                )
    assert result.status == "success"
    cache_get.assert_called_once()
    cache_put.assert_not_called()
    mock_build_graph.assert_not_called()


@patch("duckclaw.workers.factory.build_worker_graph")
def test_invoke_delegated_worker_success_with_report_id(mock_build_graph: MagicMock) -> None:
    from duckclaw.workers.worker_invoke import invoke_delegated_worker
    from langchain_core.messages import ToolMessage

    graph = MagicMock()
    graph.invoke.return_value = {
        "reply": "Dashboard listo.",
        "messages": [
            ToolMessage(
                content='{"status": "success", "report_id": "chat-abc"}',
                name="publish_custom_report",
                tool_call_id="1",
            )
        ],
    }
    mock_build_graph.return_value = graph

    caller_spec = SimpleNamespace(allowed_delegates=("worker_b",))
    with patch("duckclaw.workers.manifest.load_manifest", return_value=SimpleNamespace(forge_vault_binding=None)):
        with patch("duckclaw.manager.manager_worker_cache.worker_graph_cache_get", return_value=None):
            result = invoke_delegated_worker(
            caller_worker_id="worker_a",
            caller_spec=caller_spec,
            target_worker_id="worker_b",
            task="report_id=chat-abc publish html dashboard",
            state={"chat_id": "chat-abc", "tenant_id": "default", "user_id": "u1"},
            db=MagicMock(),
            llm=MagicMock(),
            templates_root=None,
            tenant_id="default",
        )
    assert result.status == "success"
    assert result.report_id == "chat-abc"
    assert "Dashboard" in result.reply


def test_build_worker_tools_omits_write_output_when_allowed_delegates() -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    spec = WorkerSpec(
        worker_id="worker_a",
        logical_worker_id="worker_a",
        name="wa",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.1,
        topology="general",
        skills_list=["read_sql"],
        allowed_tables=[],
        read_only=True,
        worker_dir=Path("/tmp"),
        allowed_delegates=("worker_b",),
    )
    tools = _build_worker_tools(MagicMock(), spec)  # type: ignore[arg-type]
    names = {t.name for t in tools}
    assert "invoke_worker" in names
    assert "write_output_document" not in names


def test_dashboard_html_intent_forces_invoke_worker() -> None:
    from duckclaw.workers.tool_orchestration import match_intent, parse_tool_orchestration

    spec = SimpleNamespace(
        tool_orchestration_config={
            "intents": {
                "dashboard_html": {
                    "patterns": ["(?i)dashboard.*html"],
                    "force_first_tool": "invoke_worker",
                }
            }
        }
    )
    orch = parse_tool_orchestration(spec)
    assert orch is not None
    assert match_intent("Generá y publicá un dashboard HTML con métricas", orch) == "dashboard_html"
