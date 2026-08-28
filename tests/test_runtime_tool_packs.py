from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _tool(name: str):
    return SimpleNamespace(name=name)


def _spec(**runtime_packs):
    return SimpleNamespace(tool_surface_config={"runtime_packs": dict(runtime_packs)})


@pytest.fixture(autouse=True)
def _clear_catalog_cache() -> None:
    from duckclaw.workers.tool_pack_catalog import clear_runtime_tool_pack_catalog_cache

    clear_runtime_tool_pack_catalog_cache()
    yield
    clear_runtime_tool_pack_catalog_cache()


def test_default_catalog_is_multi_agent_sota() -> None:
    from duckclaw.workers.tool_pack_catalog import load_default_runtime_tool_pack_catalog
    from duckclaw.workers.tool_pack_policy import enrich_catalog_with_mcp_connectors

    catalog = load_default_runtime_tool_pack_catalog()
    ids = {p.pack_id for p in catalog.packs}
    assert catalog.orphan_policy == "exclude"
    assert catalog.max_bound_tools <= 64
    assert catalog.max_bound_tools >= 36
    assert "core" in ids
    assert "homeostasis" in ids
    assert "mcp" in ids
    assert "knowledge" in ids
    assert "sandbox" in ids
    assert catalog.packs_for_tool("assess_crons_alignment") == frozenset({"homeostasis"})
    assert catalog.packs_for_tool("request_homeostasis_validation") == frozenset({"homeostasis"})
    # Umbrella mcp no posee members: la membresía es por conector (dinámica).
    assert catalog.packs_for_tool("mcp__github__list_issues") == frozenset()
    enriched = enrich_catalog_with_mcp_connectors(
        catalog,
        ["mcp__github__list_issues", "mcp__notion_ws__query"],
    )
    assert enriched.packs_for_tool("mcp__github__list_issues") == frozenset({"mcp_github"})
    assert enriched.packs_for_tool("mcp__notion_ws__query") == frozenset({"mcp_notion_ws"})
    android_enriched = enrich_catalog_with_mcp_connectors(
        catalog,
        ["mcp__android__get_ui_dump", "android_expand_notifications"],
    )
    assert android_enriched.packs_for_tool("mcp__android__get_ui_dump") == frozenset(
        {"mcp_android"}
    )
    assert android_enriched.packs_for_tool("android_expand_notifications") == frozenset(
        {"mcp_android"}
    )
    assert catalog.packs_for_tool("create_blank_document") == frozenset({"reports"})
    assert catalog.packs_for_tool("list_tool_packs") == frozenset({"core"})
    assert catalog.packs_for_tool("update_system_prompt") == frozenset({"core"})


def test_update_system_prompt_always_bound_in_core() -> None:
    """Platform default: every worker keeps update_system_prompt without unlock."""
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("read_sql"),
        _tool("admin_sql"),
        _tool("list_tool_packs"),
        _tool("update_system_prompt"),
        _tool("update_my_system_prompt"),
        _tool("record_operational_lesson"),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="portfolio shy bonds",
        messages=[],
    )
    assert "update_system_prompt" in result.bound_names
    assert "update_my_system_prompt" in result.bound_names
    assert "admin_sql" in result.bound_names
    assert "core" in result.active_packs
    assert "prompt_meta" not in result.active_packs


def test_homeostasis_loop_tools_always_bound() -> None:
    """ /loop SYSTEM_EVENT must see alignment + HITL tools without unlock."""
    from duckclaw.workers.tool_pack_catalog import load_default_runtime_tool_pack_catalog
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    catalog = load_default_runtime_tool_pack_catalog()
    assert "homeostasis" in {p.pack_id for p in catalog.packs}
    for name in (
        "assess_crons_alignment",
        "manage_homeostasis_goals",
        "request_homeostasis_validation",
        "homeostasis_check",
        "evaluate_homeostasis",
        "configure_loop_homeostasis",
        "get_loop_homeostasis_status",
        "calculate_tp_sl_distance",
    ):
        assert catalog.packs_for_tool(name) == frozenset({"homeostasis"})

    tools = [
        _tool("read_sql"),
        _tool("list_tool_packs"),
        _tool("assess_crons_alignment"),
        _tool("request_homeostasis_validation"),
        _tool("manage_homeostasis_goals"),
        _tool("homeostasis_check"),
        _tool("evaluate_homeostasis"),
        _tool("configure_loop_homeostasis"),
        _tool("get_loop_homeostasis_status"),
        _tool("calculate_tp_sl_distance"),
        _tool("calculate_pnl_contribution"),
        _tool("external_orphan_tool"),  # orphan unless some pack claims it
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="hello",
        messages=[],
    )
    assert "homeostasis" in result.active_packs
    assert "assess_crons_alignment" in result.bound_names
    assert "request_homeostasis_validation" in result.bound_names
    assert "manage_homeostasis_goals" in result.bound_names
    assert "evaluate_homeostasis" in result.bound_names
    assert "calculate_tp_sl_distance" in result.bound_names
    assert "external_orphan_tool" not in result.bound_names


def test_exclude_orphans_hides_unmanaged_mcp_noise() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("read_sql"),
        _tool("list_tool_packs"),
        _tool("search_project_knowledge"),
        _tool("mcp__github__list_issues"),
        _tool("mcp__slack__post_message"),
        _tool("mystery_unmanaged_tool"),
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
    assert "mcp__github__list_issues" not in names
    assert "mcp__slack__post_message" not in names
    assert "mystery_unmanaged_tool" not in names


def test_mcp_pack_activates_only_mentioned_connector() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("list_tool_packs"),
        _tool("mcp__github__list_issues"),
        _tool("mcp__notion__search"),
        _tool("search_project_knowledge"),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="lista issues abiertos en github",
        messages=[],
    )
    assert "mcp_github" in result.active_packs
    assert "mcp_notion" not in result.active_packs
    assert "mcp__github__list_issues" in result.bound_names
    assert "mcp__notion__search" not in result.bound_names
    assert "search_project_knowledge" not in result.bound_names
    assert result.connector_ids == frozenset({"github", "notion"})
    assert result.bound_count == len(result.bound_names)
    assert result.metrics["truncated"] is False
    assert result.metrics["bound_count"] == result.bound_count
    assert set(result.metrics["connector_ids"]) == {"github", "notion"}


def test_pack_id_mention_does_not_activate_connector() -> None:
    """Citar mcp_github / listar packs no debe activar tools del conector."""
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("list_tool_packs"),
        _tool("mcp__github__list_issues"),
        _tool("mcp__tavily__search"),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text=(
            "llama SOLO list_tool_packs y responde pack_id que empiecen por mcp "
            "(mcp, mcp_github, mcp_tavily). nada mas."
        ),
        messages=[],
    )
    assert "mcp_github" not in result.active_packs
    assert "mcp_tavily" not in result.active_packs
    assert "mcp__github__list_issues" not in result.bound_names
    assert "mcp__tavily__search" not in result.bound_names
    assert "list_tool_packs" in result.bound_names


def test_unlock_mcp_umbrella_exposes_all_connector_tools() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("mcp__acme__do_thing"),
        _tool("mcp__other__x"),
    ]
    messages = [
        HumanMessage(content="necesito el conector"),
        ToolMessage(
            content=json.dumps(
                {"ok": True, "pack_id": "mcp", "unlocked_packs": ["mcp"]}
            ),
            tool_call_id="1",
            name="unlock_tool_pack",
        ),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="necesito el conector",
        messages=messages,
    )
    assert "mcp" in result.active_packs
    assert "mcp_acme" in result.active_packs
    assert "mcp_other" in result.active_packs
    assert "mcp__acme__do_thing" in result.bound_names
    assert "mcp__other__x" in result.bound_names


def test_unlock_single_connector_pack_is_narrow() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("mcp__github__list_issues"),
        _tool("mcp__slack__post_message"),
    ]
    messages = [
        HumanMessage(content="github"),
        ToolMessage(
            content=json.dumps(
                {
                    "ok": True,
                    "pack_id": "mcp_github",
                    "unlocked_packs": ["mcp_github"],
                }
            ),
            tool_call_id="1",
            name="unlock_tool_pack",
        ),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="ok",
        messages=messages,
    )
    assert "mcp__github__list_issues" in result.bound_names
    assert "mcp__slack__post_message" not in result.bound_names


def test_bind_surface_metrics_on_noop() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    result = apply_runtime_tool_packs(
        [_tool("read_sql")],
        spec=_spec(enabled=False),
        intent_text="hola",
        messages=[],
    )
    assert result.applied is False
    assert result.bound_count == 1
    assert result.connector_ids == frozenset()
    assert result.metrics["applied"] is False


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


def test_disabled_runtime_packs_is_noop() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("patch_report_section"), _tool("mcp__x__y")]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=False),
        intent_text="hola",
        messages=[],
    )
    assert result.applied is False
    assert set(result.bound_names) == {"patch_report_section", "mcp__x__y"}


def test_manifest_can_opt_into_orphan_include() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [_tool("get_project_context"), _tool("legacy_unmanaged")]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True, orphan_policy="include"),
        intent_text="hola",
        messages=[],
    )
    assert "legacy_unmanaged" in result.bound_names


def test_truncate_prefers_core_and_active_over_mcp_flood() -> None:
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("search_project_knowledge"),
        _tool("list_disk_folder"),
        _tool("read_sql"),
        _tool("inspect_schema"),
        _tool("list_tool_packs"),
        _tool("unlock_tool_pack"),
    ]
    tools.extend(_tool(f"mcp__noise__t{i}") for i in range(40))
    result = apply_runtime_tool_packs(
        tools,
        # Forzar pack mcp siempre activo: flood de N conectores en el bind.
        spec=_spec(enabled=True, max_bound_tools=10, extra_always=["mcp"]),
        intent_text="busca en el vault conocimiento",
        messages=[],
    )
    assert result.truncated is True
    assert "get_project_context" in result.bound_names
    assert "search_project_knowledge" in result.bound_names
    # Core/knowledge primero; MCP rellena el resto del cupo.
    assert sum(1 for n in result.bound_names if n.startswith("mcp__")) <= 7


def test_truncate_prefers_recently_unlocked_mcp_pack() -> None:
    """Unlock mcp_android must keep android tools even if github flood is also active."""
    from langchain_core.messages import HumanMessage, ToolMessage

    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_project_context"),
        _tool("read_sql"),
        _tool("list_tool_packs"),
        _tool("unlock_tool_pack"),
        _tool("android_expand_notifications"),
        _tool("mcp__android__get_ui_dump"),
        _tool("mcp__android__swipe_screen"),
    ]
    tools.extend(_tool(f"mcp__github__t{i}") for i in range(30))
    messages = [
        HumanMessage(content="revisa notificaciones android"),
        ToolMessage(
            content='{"ok": true, "pack_id": "mcp_android", "unlocked": "mcp_android",'
            ' "unlocked_packs": ["mcp_android"]}',
            tool_call_id="1",
            name="unlock_tool_pack",
        ),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True, max_bound_tools=10, extra_always=["mcp"]),
        intent_text="revisa notificaciones android",
        messages=messages,
    )
    assert result.truncated is True
    assert "mcp__android__get_ui_dump" in result.bound_names
    assert "android_expand_notifications" in result.bound_names
    assert "mcp__android__swipe_screen" in result.bound_names


def test_android_pack_fits_full_notification_surface() -> None:
    """core+homeostasis+android MCP+ADB helpers must fit default max_bound."""
    from duckclaw.workers.tool_pack_policy import apply_runtime_tool_packs

    tools = [
        _tool("get_current_time"),
        _tool("read_sql"),
        _tool("admin_sql"),
        _tool("inspect_schema"),
        _tool("list_tool_packs"),
        _tool("unlock_tool_pack"),
        _tool("get_project_context"),
        _tool("update_system_prompt"),
        _tool("update_my_system_prompt"),
        _tool("homeostasis_check"),
        _tool("assess_crons_alignment"),
        _tool("manage_homeostasis_goals"),
        _tool("configure_loop_homeostasis"),
        _tool("get_loop_homeostasis_status"),
        _tool("request_homeostasis_validation"),
        _tool("android_expand_notifications"),
        _tool("android_collapse_notifications"),
    ]
    for name in (
        "list_devices",
        "get_device_status",
        "clear_device_session",
        "list_active_sessions",
        "get_logcat_output",
        "get_screenshot",
        "get_ui_dump",
        "click_ui_element",
        "tap_screen",
        "swipe_screen",
        "send_text",
        "perform_system_action",
    ):
        tools.append(_tool(f"mcp__android__{name}"))
    result = apply_runtime_tool_packs(
        tools,
        spec=_spec(enabled=True),
        intent_text="revisa notificaciones del android",
        messages=[],
    )
    assert "android_expand_notifications" in result.bound_names
    assert "mcp__android__get_ui_dump" in result.bound_names
    assert "mcp__android__swipe_screen" in result.bound_names
    assert result.truncated is False


def test_meta_tools_register_and_unlock() -> None:
    from duckclaw.forge.skills.tool_pack_bridge import register_tool_pack_meta_tools

    tools: list = [_tool("mcp__github__list_issues"), _tool("mcp__slack__x")]
    register_tool_pack_meta_tools(tools, spec=_spec(enabled=True))
    by_name = {t.name: t for t in tools}
    assert "list_tool_packs" in by_name
    assert "unlock_tool_pack" in by_name
    listed = json.loads(by_name["list_tool_packs"].invoke({}))
    assert listed["ok"] is True
    pack_ids = {p["pack_id"] for p in listed["packs"]}
    assert "mcp" in pack_ids
    assert "mcp_github" in pack_ids
    assert "mcp_slack" in pack_ids
    unlocked = json.loads(by_name["unlock_tool_pack"].invoke({"pack_id": "mcp"}))
    assert unlocked["ok"] is True
    assert "mcp_github" in unlocked["unlocked_packs"]
    assert "mcp_slack" in unlocked["unlocked_packs"]


def test_intent_mentions_token_word_boundary() -> None:
    from duckclaw.workers.tool_pack_policy import intent_mentions_token

    assert intent_mentions_token("issues en github hoy", "github") is True
    assert intent_mentions_token("pack mcp_github y mcp_tavily", "github") is False
    assert intent_mentions_token("pack mcp_github y mcp_tavily", "tavily") is False
    assert intent_mentions_token("busca con tavily", "tavily") is True


def test_mcp_connector_ids_parser() -> None:
    from duckclaw.workers.tool_pack_policy import mcp_connector_ids_from_tool_names

    ids = mcp_connector_ids_from_tool_names(
        ["mcp__github__list_issues", "mcp__my_notion__query", "read_sql"]
    )
    assert ids == frozenset({"github", "my_notion"})
