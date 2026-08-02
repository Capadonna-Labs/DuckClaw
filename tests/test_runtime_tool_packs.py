from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _tool(name: str):
    return SimpleNamespace(name=name)


def _spec(**runtime_packs):
    return SimpleNamespace(tool_surface_config={"runtime_packs": dict(runtime_packs)})


def test_default_catalog_loads_core_and_knowledge() -> None:
    from duckclaw.workers.tool_pack_catalog import (
        clear_runtime_tool_pack_catalog_cache,
        load_default_runtime_tool_pack_catalog,
    )

    clear_runtime_tool_pack_catalog_cache()
    catalog = load_default_runtime_tool_pack_catalog()
    ids = {p.pack_id for p in catalog.packs}
    assert "core" in ids
    assert "knowledge" in ids
    assert "reports" in ids
    assert catalog.packs_for_tool("patch_report_section") == frozenset({"reports"})
    assert catalog.packs_for_tool("list_disk_folder") == frozenset({"knowledge"})
    assert catalog.packs_for_tool("list_tool_packs") == frozenset({"core"})


def test_filter_hides_reports_on_knowledge_intent() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("read_sql"),
        _tool("list_tool_packs"),
        _tool("search_project_knowledge"),
        _tool("patch_report_section"),
        _tool("web_search"),
        _tool("some_mcp_custom_tool"),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="busca en el vault el documento de IAM",
        messages=[],
    )
    names = set(result.bound_names)
    assert result.applied is True
    assert "search_project_knowledge" in names
    assert "get_project_context" in names
    assert "patch_report_section" not in names
    assert "web_search" not in names
    # orphan MCP tool stays (orphan_policy include)
    assert "some_mcp_custom_tool" in names


def test_sticky_keeps_reports_after_tool_use() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("patch_report_section"),
        _tool("render_report_instance"),
    ]
    messages = [
        HumanMessage(content="sigue con el informe"),
        ToolMessage(
            content='{"ok": true}',
            tool_call_id="1",
            name="patch_report_section",
        ),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="ok",
        messages=messages,
    )
    assert "patch_report_section" in result.bound_names
    assert "render_report_instance" in result.bound_names
    assert "reports" in result.active_packs


def test_unlock_tool_message_activates_pack() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("get_project_context"), _tool("web_search"), _tool("unlock_tool_pack")]
    messages = [
        HumanMessage(content="necesito internet"),
        ToolMessage(
            content=json.dumps(
                {"ok": True, "pack_id": "research", "unlocked_packs": ["research"]}
            ),
            tool_call_id="1",
            name="unlock_tool_pack",
        ),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="necesito internet",
        messages=messages,
    )
    assert "web_search" in result.bound_names
    assert "research" in result.active_packs


def test_disabled_runtime_packs_is_noop() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("patch_report_section"), _tool("web_search")]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=False),
        intent_text="hola",
        messages=[],
    )
    assert result.applied is False
    assert set(result.bound_names) == {"patch_report_section", "web_search"}


def test_manifest_pack_override_activation_signal() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("get_project_context"), _tool("web_search")]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(
            enabled=True,
            pack_overrides={"research": {"activation_signals": ["zorglub-signal"]}},
        ),
        intent_text="por favor zorglub-signal ahora",
        messages=[],
    )
    assert "web_search" in result.bound_names


def test_meta_tools_register_and_unlock() -> None:
    from duckclaw.forge.skills.tool_pack_bridge import register_tool_pack_meta_tools

    tools: list = []
    register_tool_pack_meta_tools(tools, spec=_spec(enabled=True))
    by_name = {t.name: t for t in tools}
    assert "list_tool_packs" in by_name
    assert "unlock_tool_pack" in by_name
    listed = json.loads(by_name["list_tool_packs"].invoke({}))
    assert listed["ok"] is True
    assert any(p["pack_id"] == "knowledge" for p in listed["packs"])
    unlocked = json.loads(by_name["unlock_tool_pack"].invoke({"pack_id": "reports"}))
    assert unlocked["ok"] is True
    assert unlocked["pack_id"] == "reports"
    bad = json.loads(by_name["unlock_tool_pack"].invoke({"pack_id": "nope"}))
    assert bad["ok"] is False


def test_truncate_prefers_active_packs_over_orphans() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    # Many unmanaged MCP-like tools would previously crowd out knowledge tools.
    tools = [_tool("get_project_context"), _tool("search_project_knowledge"), _tool("list_disk_folder")]
    tools.extend(_tool(f"mcp_noise_{i}") for i in range(40))
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True, max_bound_tools=10),
        intent_text="busca en el vault conocimiento",
        messages=[],
    )
    assert result.truncated is True
    assert "get_project_context" in result.bound_names
    assert "search_project_knowledge" in result.bound_names
    assert "list_disk_folder" in result.bound_names
    # Orphans only fill remaining slots after active packs.
    assert sum(1 for n in result.bound_names if n.startswith("mcp_noise_")) <= 7

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("get_project_context"), _tool("mystery_tool")]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True, orphan_policy="exclude"),
        intent_text="hola",
        messages=[],
    )
    assert "get_project_context" in result.bound_names
    assert "mystery_tool" not in result.bound_names
