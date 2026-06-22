"""Tests for generic external worker tool-context extension hooks."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from duckclaw.extensions.tool_context import (
    get_worker_tool_context_hooks,
    invalidate_extension_tool_context_cache,
    invoke_extension_worker_tool_context_hooks,
)


@pytest.fixture
def tool_context_extension_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").write_text("", encoding="utf-8")
    (lib / "fake_tool_context.py").write_text(
        textwrap.dedent(
            """
            _bound = []

            def bind_worker_tool_context(*, chat_id, integration_label, **kwargs):
                _bound.append({"chat_id": chat_id, "integration_label": integration_label})
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "fly_extension.yaml"
    manifest.write_text(
        textwrap.dedent(
            """
            lib_path: lib
            package_name: test_tool_ctx_ext
            worker_tool_context_hooks:
              - fake_tool_context:bind_worker_tool_context
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_FLY_MANIFEST", str(manifest))
    monkeypatch.delenv("DUCKCLAW_WORKER_TOOL_CONTEXT_HOOKS", raising=False)
    invalidate_extension_tool_context_cache()
    yield tmp_path
    invalidate_extension_tool_context_cache()


def test_worker_tool_context_hooks_loaded(tool_context_extension_sandbox: Path) -> None:
    hooks = get_worker_tool_context_hooks()
    assert len(hooks) == 1


def test_invoke_worker_tool_context_hooks_passes_state(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def recording_hook(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "duckclaw.extensions.tool_context.get_worker_tool_context_hooks",
        lambda: [recording_hook],
    )
    state = {"chat_id": "admin-conv-abc", "integration_label": "Interfaz"}
    invoke_extension_worker_tool_context_hooks(
        state=state,
        spec=object(),
        db=type("Db", (), {"_path": "/tmp/test.duckdb"})(),
        logical_worker_id="sample-worker",
        worker_path="/tmp/test.duckdb",
        chat_id="admin-conv-abc",
        tenant_id="default",
        user_id="u1",
        integration_channel="http",
        integration_label="Interfaz",
    )
    assert captured.get("chat_id") == "admin-conv-abc"
    assert captured.get("integration_label") == "Interfaz"
    assert captured.get("db_path") == "/tmp/test.duckdb"
