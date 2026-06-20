"""Sandbox registers when LLM is present even without pre-existing security_policy.yaml."""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel


class _BindableFakeLLM(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _write_worker(tmp_path: Path) -> Path:
    worker_dir = tmp_path / "templates" / "workers" / "default"
    worker_dir.mkdir(parents=True)
    worker_dir.joinpath("manifest.yaml").write_text(
        "name: smoke\nid: default\ntopology: general\nskills: []\n",
        encoding="utf-8",
    )
    worker_dir.joinpath("system_prompt.md").write_text("Eres un agente de prueba.", encoding="utf-8")
    return tmp_path


def test_run_sandbox_registered_without_security_policy_file(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context

    root = _write_worker(tmp_path)
    worker_dir = root / "templates" / "workers" / "default"
    assert not (worker_dir / "security_policy.yaml").is_file()

    ctx = initialize_worker_graph_context(
        "default",
        ":memory:",
        _BindableFakeLLM(responses=["ok"]),
        templates_root=root,
        llm_provider="none_llm",
    )
    assert "run_sandbox" in (ctx.tools_by_name or {})
    assert (worker_dir / "security_policy.yaml").is_file()
