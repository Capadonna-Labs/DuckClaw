from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERAL_GRAPH = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs" / "general_graph.py"
CHAT_HEARTBEAT = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs" / "chat_heartbeat.py"


def test_general_graph_tool_catalog_defaults_are_safe_without_db_policy() -> None:
    from duckclaw.graphs.tool_catalog import (
        ADMIN_HEARTBEAT_SQL_TOOL_NAMES,
        DEFAULT_GENERAL_SYSTEM_PROMPT,
        DEFAULT_GENERAL_TOOL_NAMES,
        default_general_tool_names,
        heartbeat_message_for_tool_name,
    )

    assert DEFAULT_GENERAL_SYSTEM_PROMPT.strip()
    assert default_general_tool_names(None) == DEFAULT_GENERAL_TOOL_NAMES
    assert "read_sql" in DEFAULT_GENERAL_TOOL_NAMES
    assert "inspect_schema" in DEFAULT_GENERAL_TOOL_NAMES
    assert "get_db_path" in DEFAULT_GENERAL_TOOL_NAMES
    assert "admin_sql" not in DEFAULT_GENERAL_TOOL_NAMES
    assert "run_sandbox" not in DEFAULT_GENERAL_TOOL_NAMES
    assert "manage_memory" not in DEFAULT_GENERAL_TOOL_NAMES
    assert "admin_sql" in ADMIN_HEARTBEAT_SQL_TOOL_NAMES
    assert "read_sql" in ADMIN_HEARTBEAT_SQL_TOOL_NAMES
    assert "sql" in heartbeat_message_for_tool_name("read_sql").lower()
    assert "custom_xyz" in heartbeat_message_for_tool_name("custom_xyz")


def test_general_graph_uses_tool_catalog_for_runtime_defaults() -> None:
    text = GENERAL_GRAPH.read_text(encoding="utf-8")

    assert "from duckclaw.guardrails.loader import load_guardrail" not in text
    assert "_DEFAULT_TOOLS" not in text
    assert "DEFAULT_GENERAL_SYSTEM_PROMPT" in text
    assert "default_general_tool_names" in text
    assert "from duckclaw.workers.tool_surface_policy import" in text
    assert "_general_auto_bind_tools(" in text
    assert "_general_db_bind_tools(" in text
    assert "without_privileged_mutation_tools(auto_tools)" in text
    assert "without_storage_identity_tools(auto_tools)" in text
    assert "without_sandbox_tools(auto_tools)" in text


def test_general_graph_db_intent_is_not_any_question_or_vertical_example() -> None:
    from duckclaw.graphs.general_graph import _needs_db_tool

    assert not _needs_db_tool("hola?")
    assert not _needs_db_tool("qué puedes hacer?")
    assert _needs_db_tool("qué tablas hay en la base?")
    assert _needs_db_tool("usa read_sql para consultar la tabla")

    text = GENERAL_GRAPH.read_text(encoding="utf-8").lower()
    for marker in ("ventas", "vendedor", "clientes", "productos", "pedidos", "seller"):
        assert marker not in text


def test_general_graph_auto_bind_hides_sensitive_tools() -> None:
    from dataclasses import dataclass

    from duckclaw.graphs.general_graph import _general_auto_bind_tools, _general_db_bind_tools

    @dataclass(frozen=True)
    class ToolStub:
        name: str

    tools = [
        ToolStub("read_sql"),
        ToolStub("admin_sql"),
        ToolStub("inspect_schema"),
        ToolStub("get_db_path"),
        ToolStub("run_sandbox"),
        ToolStub("search_knowledge"),
    ]

    assert [tool.name for tool in _general_auto_bind_tools(tools, "hola")] == [
        "read_sql",
        "inspect_schema",
        "search_knowledge",
    ]
    assert "get_db_path" in [
        tool.name
        for tool in _general_auto_bind_tools(
            tools,
            "qué base de datos estás usando?",
        )
    ]
    assert "run_sandbox" in [
        tool.name
        for tool in _general_auto_bind_tools(
            tools,
            "ejecuta este código python",
        )
    ]
    assert [tool.name for tool in _general_db_bind_tools(tools, "qué tablas hay?")] == [
        "read_sql",
        "inspect_schema",
        "search_knowledge",
    ]
    assert "get_db_path" in [
        tool.name
        for tool in _general_db_bind_tools(
            tools,
            "qué base de datos estás usando?",
        )
    ]


def test_chat_heartbeat_sql_tools_are_catalog_alias() -> None:
    from duckclaw.graphs import chat_heartbeat
    from duckclaw.graphs.tool_catalog import ADMIN_HEARTBEAT_SQL_TOOL_NAMES

    text = CHAT_HEARTBEAT.read_text(encoding="utf-8")
    assert "ADMIN_SQL_TOOL_NAMES: frozenset[str] = frozenset(" not in text
    assert chat_heartbeat.ADMIN_SQL_TOOL_NAMES is ADMIN_HEARTBEAT_SQL_TOOL_NAMES


def test_chat_heartbeat_uses_catalog_messages_without_vertical_examples() -> None:
    text = CHAT_HEARTBEAT.read_text(encoding="utf-8")

    assert "load_guardrail_kv" not in text
    for marker in ("BI-Analyst", "SIATA", "platform-orchestrator"):
        assert marker not in text
