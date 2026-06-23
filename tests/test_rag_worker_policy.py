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
from duckclaw.workers.tool_surface_policy import (
    should_hide_sandbox_tools,
    should_hide_storage_identity_tools,
    tool_surface_intent_text,
    without_sandbox_tools,
    without_privileged_mutation_tools,
    without_privileged_mutation_tools_for_auto_bind,
    without_storage_identity_tools,
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


def test_plain_greeting_hides_storage_identity_tools_from_auto_bind() -> None:
    tools = [
        ToolStub("read_sql"),
        ToolStub("inspect_schema"),
        ToolStub("get_db_path"),
        ToolStub("search_knowledge"),
    ]

    assert should_hide_storage_identity_tools(
        "hola",
        "hola",
        explicit_storage_request=lambda text: "duckdb" in text.lower(),
    )
    assert [tool.name for tool in without_storage_identity_tools(tools)] == [
        "read_sql",
        "inspect_schema",
        "search_knowledge",
    ]


def test_explicit_db_identity_request_keeps_get_db_path_available() -> None:
    assert not should_hide_storage_identity_tools(
        "qué base de datos estás usando?",
        "qué base de datos estás usando?",
        explicit_storage_request=lambda text: "duckdb" in text.lower(),
    )
    assert not should_hide_storage_identity_tools(
        "cuál es la ruta del duckdb?",
        "cuál es la ruta del duckdb?",
        explicit_storage_request=lambda text: "duckdb" in text.lower(),
    )
    assert not should_hide_storage_identity_tools(
        "[PROJECT_CONTEXT]\nbase de datos interna\n[/PROJECT_CONTEXT]\nque BD usas",
        "que BD usas",
        explicit_storage_request=lambda text: "duckdb" in text.lower(),
    )


def test_tool_surface_intent_prefers_original_user_text_over_injected_context() -> None:
    injected_context = (
        "[PROJECT_CONTEXT]\n"
        "Nombre: AWS EXPERT\n"
        "DuckDB: /private/project.duckdb\n"
        "[/PROJECT_CONTEXT]\n"
        "hola"
    )

    assert tool_surface_intent_text("hola", injected_context) == "hola"
    assert tool_surface_intent_text("", injected_context) == injected_context


def test_schema_request_still_hides_storage_identity_tools() -> None:
    assert should_hide_storage_identity_tools(
        "qué tablas hay en la base?",
        "qué tablas hay en la base?",
        explicit_storage_request=lambda text: "tablas" in text.lower(),
    )


def test_auto_bind_hides_privileged_mutation_tools() -> None:
    tools = [
        ToolStub("read_sql"),
        ToolStub("admin_sql"),
        ToolStub("inspect_schema"),
        ToolStub("search_knowledge"),
    ]

    assert [tool.name for tool in without_privileged_mutation_tools(tools)] == [
        "read_sql",
        "inspect_schema",
        "search_knowledge",
    ]


def test_manifest_can_expose_privileged_mutation_tools_in_auto_bind() -> None:
    tools = [
        ToolStub("read_sql"),
        ToolStub("admin_sql"),
        ToolStub("inspect_schema"),
    ]
    spec = type(
        "Spec",
        (),
        {"tool_surface_config": {"expose_privileged_mutation_tools": ["admin_sql"]}},
    )()

    assert [tool.name for tool in without_privileged_mutation_tools_for_auto_bind(tools, spec=spec)] == [
        "read_sql",
        "admin_sql",
        "inspect_schema",
    ]


def test_plain_greeting_hides_sandbox_tools_from_auto_bind() -> None:
    tools = [
        ToolStub("read_sql"),
        ToolStub("run_sandbox"),
        ToolStub("run_browser_sandbox"),
        ToolStub("get_browser_session_url"),
        ToolStub("search_knowledge"),
    ]

    assert should_hide_sandbox_tools("hola", "hola")
    assert [tool.name for tool in without_sandbox_tools(tools)] == [
        "read_sql",
        "search_knowledge",
    ]


def test_explicit_execution_or_browser_intent_keeps_sandbox_tools_available() -> None:
    assert not should_hide_sandbox_tools("ejecuta este código python", "ejecuta este código python")
    assert not should_hide_sandbox_tools("abre https://example.com en el navegador", "abre https://example.com")


def test_rag_turn_prompt_inherits_default_with_tenant_id_placeholder() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        "UPDATE main.prompt_policy_registry SET content = ? "
        "WHERE policy_type = 'system_prompt' AND policy_name = 'default'",
        ["Workspace {tenant_id} worker {worker_id}"],
    )
    con.execute("DELETE FROM main.prompt_policy_registry WHERE policy_name = 'rag_turn'")

    prompt = rag_turn_system_prompt(
        PromptPolicyResolver(db=con),
        "aws-expert-agent",
        tenant_id="tenant_test",
    )

    assert "tenant_test" in prompt
    assert "aws-expert-agent" in prompt


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
    factory_invoke = Path(
        "packages/agents/src/duckclaw/workers/factory_graph_nodes_agent_invoke.py"
    ).read_text(encoding="utf-8")

    assert "from duckclaw.forge.rag.tool_policy import" in factory_invoke
    assert "from duckclaw.forge.rag.prompt_policy import" in factory_invoke
    assert "from duckclaw.workers.tool_surface_policy import" in factory_invoke
    assert "should_prioritize_rag_over_storage_tools(" in factory_invoke
    assert "should_hide_storage_identity_tools(" in factory_invoke
    assert "_auto_tools = without_storage_identity_tools(_auto_tools)" in factory_invoke
    assert "without_privileged_mutation_tools_for_auto_bind(" in factory_invoke
    assert "_auto_tools = without_sandbox_tools(_auto_tools)" in factory_invoke
    assert "_auto_tools = without_storage_tools(_auto_tools)" in factory_invoke
    assert "rag_turn_system_prompt(" in factory_invoke


def test_rag_tool_policy_lives_in_rag_package_not_workers() -> None:
    assert Path("packages/agents/src/duckclaw/forge/rag/tool_policy.py").exists()
    assert not Path("packages/agents/src/duckclaw/workers/rag_policy.py").exists()


def test_storage_identity_policy_lives_in_worker_tool_surface_owner() -> None:
    rag_policy = Path("packages/agents/src/duckclaw/forge/rag/tool_policy.py").read_text(encoding="utf-8")
    worker_policy_path = Path("packages/agents/src/duckclaw/workers/tool_surface_policy.py")

    assert worker_policy_path.exists()
    assert "STORAGE_IDENTITY_TOOL_NAMES" not in rag_policy
    assert "should_hide_storage_identity_tools" not in rag_policy
