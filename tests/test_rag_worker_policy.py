from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from duckclaw.forge.rag.prompt_policy import rag_turn_system_prompt
from duckclaw.forge.rag.tool_policy import (
    has_rag_context,
    should_prioritize_rag_over_storage_tools,
    without_storage_tools,
)


@dataclass(frozen=True)
class ToolStub:
    name: str


def test_rag_turn_without_storage_intent_hides_storage_tools() -> None:
    incoming = "[RAG_CONTEXT]\nClean Code habla de nombres claros.\n[/RAG_CONTEXT]\nclean code?"

    assert has_rag_context(incoming)
    assert should_prioritize_rag_over_storage_tools(
        incoming,
        "clean code?",
        explicit_storage_request=lambda text: "duckdb" in text.lower(),
    )

    tools = [
        ToolStub("read_sql"),
        ToolStub("admin_sql"),
        ToolStub("inspect_schema"),
        ToolStub("get_schema_info"),
        ToolStub("get_db_path"),
        ToolStub("search_knowledge"),
    ]

    assert [tool.name for tool in without_storage_tools(tools)] == ["search_knowledge"]


def test_explicit_storage_intent_keeps_storage_tools_available() -> None:
    incoming = "[RAG_SOURCE_INVENTORY]\n- AWS docs\n[/RAG_SOURCE_INVENTORY]\nque tablas tengo?"

    assert not should_prioritize_rag_over_storage_tools(
        incoming,
        "que tablas tengo?",
        explicit_storage_request=lambda text: "tablas" in text.lower(),
    )


def test_rag_turn_prompt_avoids_storage_and_operational_menus() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    content = (
        "[MODO_RAG_CONOCIMIENTO]\n"
        "Eres {worker_id}. Usa conocimiento recuperado sin menús operativos.\n"
        "[/MODO_RAG_CONOCIMIENTO]"
    )
    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, active)
        VALUES (?, 'system_prompt', 'rag_turn', 1, 'active', ?, ?, true)
        """,
        ["system_prompt_rag_turn_1", content, hashlib.sha256(content.encode("utf-8")).hexdigest()],
    )

    prompt = rag_turn_system_prompt(
        PromptPolicyResolver(db=con),
        "ciberseguridad-agent",
    ).lower()

    assert "modo_rag_conocimiento" in prompt
    assert "conocimiento recuperado" in prompt
    assert "duckdb" not in prompt
    assert "base de datos" not in prompt
    assert "/workers" not in prompt
    assert "/tasks" not in prompt
    assert "próximos pasos" not in prompt
    assert "tarea concreta" not in prompt


def test_rag_debug_instrumentation_is_not_left_in_runtime_modules() -> None:
    runtime_paths = [
        Path("packages/agents/src/duckclaw/workers/factory.py"),
        Path("packages/agents/src/duckclaw/forge/rag/context_provider.py"),
        Path("packages/agents/src/duckclaw/graphs/manager_graph.py"),
        Path("packages/agents/src/duckclaw/graphs/graph_server.py"),
        Path("services/api-gateway/routers/admin.py"),
        Path("services/api-gateway/main.py"),
    ]
    forbidden = (
        "debug-ab0734",
        "sessionId\": \"ab0734",
        "_rag_debug_log",
        "worker-rag-debug",
        "initial-rag-debug",
        "downstream-rag-debug",
    )

    for path in runtime_paths:
        content = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in content, f"{marker!r} leaked into {path}"


def test_factory_uses_extracted_rag_policy_for_get_db_path() -> None:
    factory = Path("packages/agents/src/duckclaw/workers/factory.py").read_text(encoding="utf-8")

    assert "from duckclaw.forge.rag.tool_policy import" in factory
    assert "from duckclaw.forge.rag.prompt_policy import" in factory
    assert "should_prioritize_rag_over_storage_tools(" in factory
    assert "without_storage_tools(_bind_base_rag)" in factory
    assert "rag_turn_system_prompt(prompt_policies, _lid)" in factory


def test_rag_tool_policy_lives_in_rag_package_not_workers() -> None:
    assert Path("packages/agents/src/duckclaw/forge/rag/tool_policy.py").exists()
    assert not Path("packages/agents/src/duckclaw/workers/rag_policy.py").exists()
