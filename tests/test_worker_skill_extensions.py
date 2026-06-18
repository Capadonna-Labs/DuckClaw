"""Tests for generic external worker skill extension hooks."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from duckclaw.extensions.skills import (
    get_worker_skill_hooks,
    invalidate_extension_skills_cache,
    invoke_extension_worker_skill_hooks,
)


@pytest.fixture
def skill_extension_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").write_text("", encoding="utf-8")
    (lib / "fake_skills.py").write_text(
        textwrap.dedent(
            """
            _registered = []

            def register_worker_skills(*, tools, spec, db, llm, logical_worker_id, worker_path, **kwargs):
                tools.append(type("FakeTool", (), {"name": "fake_extension_tool"})())
                _registered.append(logical_worker_id)
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
            package_name: test_skill_ext
            worker_skill_hooks:
              - fake_skills:register_worker_skills
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_FLY_MANIFEST", str(manifest))
    monkeypatch.delenv("DUCKCLAW_WORKER_SKILL_HOOKS", raising=False)
    invalidate_extension_skills_cache()
    yield tmp_path
    invalidate_extension_skills_cache()


def test_worker_skill_hooks_loaded(skill_extension_sandbox: Path) -> None:
    hooks = get_worker_skill_hooks()
    assert len(hooks) == 1


def test_invoke_worker_skill_hooks_adds_tool(skill_extension_sandbox: Path) -> None:
    tools: list = []
    invoke_extension_worker_skill_hooks(
        tools=tools,
        spec=type("Spec", (), {"worker_id": "test", "logical_worker_id": "test"})(),
        db=object(),
        llm=None,
        logical_worker_id="test",
        worker_path="/tmp/test.duckdb",
    )
    names = [getattr(t, "name", "") for t in tools]
    assert "fake_extension_tool" in names


def test_env_only_skill_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib = tmp_path / "plugins"
    lib.mkdir()
    (lib / "env_skills.py").write_text(
        "def register_worker_skills(*, tools, **kwargs):\n"
        "    tools.append(type('T', (), {'name': 'env_skill_tool'})())\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_EXTENSION_LIB_PATH", "plugins")
    monkeypatch.setenv("DUCKCLAW_WORKER_SKILL_HOOKS", "env_skills:register_worker_skills")
    monkeypatch.delenv("DUCKCLAW_FLY_MANIFEST", raising=False)
    invalidate_extension_skills_cache()
    tools: list = []
    invoke_extension_worker_skill_hooks(
        tools=tools,
        spec=object(),
        db=object(),
        llm=None,
        logical_worker_id="w1",
        worker_path=":memory:",
    )
    assert any(getattr(t, "name", "") == "env_skill_tool" for t in tools)
    invalidate_extension_skills_cache()
