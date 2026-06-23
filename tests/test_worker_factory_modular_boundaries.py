from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


FACTORY_PATH = Path("packages/agents/src/duckclaw/workers/factory.py")


def _factory_source() -> str:
    return FACTORY_PATH.read_text(encoding="utf-8")


def _factory_function_names() -> set[str]:
    tree = ast.parse(_factory_source())
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _write_worker_manifest(root: Path, worker_id: str) -> None:
    worker_dir = root / worker_id
    worker_dir.mkdir(parents=True)
    worker_dir.joinpath("manifest.yaml").write_text(
        f"name: {worker_id}\nid: {worker_id}\ntopology: general\nskills: []\n",
        encoding="utf-8",
    )


def _write_default_worker_layout(root: Path) -> Path:
    """Filesystem layout expected by load_manifest(templates_root=root)."""
    worker_dir = root / "templates" / "workers" / "default"
    worker_dir.mkdir(parents=True, exist_ok=True)
    worker_dir.joinpath("manifest.yaml").write_text(
        "name: smoke-default\nid: default\ntopology: general\nskills: []\n",
        encoding="utf-8",
    )
    worker_dir.joinpath("system_prompt.md").write_text("Eres un agente de prueba.", encoding="utf-8")
    return worker_dir


class _FakeBindableLLM:
    """Minimal LLM stub: bind_tools returns self; invoke returns configured AIMessage."""

    def __init__(self, *, content: str = "respuesta smoke", tool_calls: list[dict[str, Any]] | None = None) -> None:
        self._content = content
        self._tool_calls = tool_calls or []

    def bind_tools(self, tools: Any, **kwargs: Any) -> _FakeBindableLLM:
        return self

    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(content=self._content, tool_calls=list(self._tool_calls))


class _AlwaysToolCallLLM:
    """LLM stub that always requests read_sql (exercises agent↔tools loop)."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> _AlwaysToolCallLLM:
        return self

    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": "read_sql", "args": {"query": "SELECT 1"}, "id": "loop-tool"}],
        )


def test_filesystem_worker_layout_exposes_only_default_template(tmp_path: Path) -> None:
    from duckclaw.workers.template_registry import build_alias_index, list_template_ids, resolve_template_id_global

    templates_root = tmp_path / "seed"
    _write_worker_manifest(templates_root, "default")
    _write_worker_manifest(templates_root, "axis-coder")

    assert list_template_ids(templates_root) == ["default"]
    assert build_alias_index(templates_root) == {"default": "default"}
    assert resolve_template_id_global("axis-coder", templates_root) is None


def test_load_manifest_rejects_non_default_filesystem_worker(tmp_path: Path) -> None:
    from duckclaw.workers.manifest import load_manifest

    legacy_root = tmp_path / "legacy"
    workers_root = legacy_root / "templates" / "workers"
    _write_worker_manifest(workers_root, "default")
    _write_worker_manifest(workers_root, "axis-coder")

    with pytest.raises(FileNotFoundError, match="Only the default filesystem worker"):
        load_manifest("axis-coder", templates_root=legacy_root)


def test_factory_list_workers_exposes_only_default_from_filesystem_layout(tmp_path: Path) -> None:
    from duckclaw.workers.factory import list_workers

    legacy_root = tmp_path / "legacy"
    workers_root = legacy_root / "templates" / "workers"
    _write_worker_manifest(workers_root, "default")
    _write_worker_manifest(workers_root, "axis-coder")

    assert list_workers(legacy_root) == ["default"]


def test_worker_discovery_owns_list_workers_with_factory_facade() -> None:
    discovery = importlib.import_module("duckclaw.workers.discovery")
    from duckclaw.workers import factory

    assert factory.list_workers is discovery.list_workers
    assert factory.list_workers.__module__ == "duckclaw.workers.discovery"
    assert "list_workers" not in _factory_function_names()


def test_visual_evidence_policy_owns_retry_limit_with_factory_facade() -> None:
    policy = importlib.import_module("duckclaw.workers.visual_evidence_policy")
    from duckclaw.workers import factory

    assert factory._visual_evidence_max_retries is policy.visual_evidence_max_retries
    assert factory._visual_evidence_max_retries.__module__ == "duckclaw.workers.visual_evidence_policy"
    assert "_visual_evidence_max_retries" not in _factory_function_names()


def test_tool_output_truncation_owns_helpers_with_factory_facade() -> None:
    truncation = importlib.import_module("duckclaw.workers.tool_output_truncation")
    from duckclaw.workers import factory

    assert factory._truncate_tool_messages is truncation.truncate_tool_messages_for_llm
    assert (
        factory._compact_run_sandbox_tool_content_for_llm
        is truncation.compact_run_sandbox_tool_content_for_llm
    )
    assert factory._truncate_tool_messages.__module__ == "duckclaw.workers.tool_output_truncation"
    assert (
        factory._compact_run_sandbox_tool_content_for_llm.__module__
        == "duckclaw.workers.tool_output_truncation"
    )
    names = _factory_function_names()
    assert "_truncate_tool_messages" not in names
    assert "_compact_run_sandbox_tool_content_for_llm" not in names


def test_provider_input_budget_owns_helpers_with_factory_facade() -> None:
    budget = importlib.import_module("duckclaw.workers.provider_input_budget")
    from duckclaw.workers import factory

    assert factory._normalized_context_pruning is budget.normalized_context_pruning
    assert factory._estimate_tokens_from_messages is budget.estimate_tokens_from_messages
    assert factory._apply_provider_input_budget is budget.apply_provider_input_budget
    assert (
        factory._configure_provider_budget_runtime_db_provider
        is budget.configure_provider_budget_runtime_db_provider
    )
    assert factory._split_for_pruning is budget.split_for_pruning
    assert factory._trim_messages_to_estimated_cap is budget.trim_messages_to_estimated_cap
    assert factory._apply_provider_input_budget.__module__ == "duckclaw.workers.provider_input_budget"
    assert factory._split_for_pruning.__module__ == "duckclaw.workers.provider_input_budget"
    names = _factory_function_names()
    assert "_normalized_context_pruning" not in names
    assert "_estimate_tokens_from_messages" not in names
    assert "_groq_max_estimated_input_tokens" not in names
    assert "_groq_tool_message_max_chars" not in names
    assert "_trim_messages_to_estimated_cap" not in names
    assert "_apply_groq_message_budget" not in names
    assert "_mlx_max_estimated_input_tokens" not in names
    assert "_mlx_tool_message_max_chars" not in names
    assert "_apply_mlx_message_budget" not in names
    assert "_apply_provider_input_budget" not in names
    assert "_split_for_pruning" not in names


def test_context_monitor_owns_summary_helpers_with_factory_facade() -> None:
    monitor = importlib.import_module("duckclaw.workers.context_monitor")
    from duckclaw.workers import factory

    assert factory._serialize_messages_for_summary is monitor.serialize_messages_for_summary
    assert factory._llm_fold_conversation_summary is monitor.llm_fold_conversation_summary
    assert factory._compose_context_summary_prompt is monitor.compose_context_summary_prompt
    assert factory._build_context_monitor_node is monitor.build_context_monitor_node
    assert factory._build_summary_llm is monitor.build_summary_llm
    assert factory._llm_fold_conversation_summary.__module__ == "duckclaw.workers.context_monitor"
    assert factory._build_context_monitor_node.__module__ == "duckclaw.workers.context_monitor"
    names = _factory_function_names()
    assert "_serialize_messages_for_summary" not in names
    assert "_llm_fold_conversation_summary" not in names
    assert "_compose_bi_system_prompt" not in names
    assert "context_monitor_node" not in names


def test_tool_binding_owns_tool_surface_helpers_with_factory_facade() -> None:
    binding = importlib.import_module("duckclaw.workers.tool_binding")
    from duckclaw.workers import factory

    assert factory.filter_tools_for_sandbox is binding.filter_tools_for_sandbox
    assert factory._groq_tools_without_reddit_for_bind is binding.groq_tools_without_reddit_for_bind
    assert factory._tool_choice_function is binding.tool_choice_function
    assert factory._tool_called_since is binding.tool_called_since
    assert factory.filter_tools_for_sandbox.__module__ == "duckclaw.workers.tool_binding"
    assert (
        factory._groq_tools_without_reddit_for_bind.__module__
        == "duckclaw.workers.tool_binding"
    )
    assert factory._tool_choice_function.__module__ == "duckclaw.workers.tool_binding"
    assert factory._tool_called_since.__module__ == "duckclaw.workers.tool_binding"
    names = _factory_function_names()
    assert "filter_tools_for_sandbox" not in names
    assert "_groq_tools_without_reddit_for_bind" not in names
    assert "_tool_called_since" not in names
    assert "_reddit_tool_choice_dict" not in names


def test_factory_context_monitor_has_no_bi_specific_compression_policy() -> None:
    source = _factory_source()
    forbidden = {
        "_compose_bi_system_prompt",
        "analista BI",
        "Analista BI",
        "Resumen analítico",
        '== "bi_analyst"',
        '!= "bi_analyst"',
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_core_admin_runtime_does_not_hardcode_non_default_platform_worker() -> None:
    hardcoded_worker_id = "platform" + "-orchestrator"
    production_paths = (
        Path("packages/shared/src/duckclaw/admin_worker_catalog.py"),
        Path("services/api-gateway/core/admin_identity.py"),
        Path("services/api-gateway/routers/admin.py"),
        Path("services/api-gateway/routers/admin_db_first.py"),
    )

    leaks = [
        str(path)
        for path in production_paths
        if hardcoded_worker_id in path.read_text(encoding="utf-8")
    ]

    assert leaks == []


def test_factory_delegates_db_runtime_and_intent_policy() -> None:
    assert Path("packages/agents/src/duckclaw/workers/db_runtime.py").exists()
    assert Path("packages/agents/src/duckclaw/workers/db_intent_policy.py").exists()

    names = _factory_function_names()
    forbidden = {
        "_escape_attach_path",
        "_same_duckdb_file",
        "_resolve_shared_db_path",
        "_apply_forge_attaches",
        "_bootstrap_shared_main_schema",
        "_infer_user_id_for_writer",
        "_get_db_path",
        "explicit_duckdb_schema_request",
        "incoming_is_schema_query_heuristic",
        "_truncate_read_sql_result_for_llm",
    }
    assert names.isdisjoint(forbidden)


def test_factory_has_no_inline_pqrsd_policy_or_tool_names() -> None:
    source = _factory_source()
    source_lower = source.lower()
    names = _factory_function_names()
    assert not any(name.startswith("_pqrsd_") for name in names)
    for marker in (
        "pqrsd",
        "pqr",
        "radicacion",
        "pqrsd_fetch_canonical",
        "pqrsd_run_identificacion_step1",
        "pqrsd_upsert_radicacion_perfil",
    ):
        assert marker not in source_lower


def test_factory_has_no_worker_id_predicate_shims() -> None:
    source = _factory_source()
    names = _factory_function_names()

    forbidden_predicates = {
        "is_finanz",
        "is_market_worker",
        "is_pqrsd_assistant",
        "is_quant_trader",
    }
    assert names.isdisjoint(forbidden_predicates)
    assert "duckclaw.workers.worker_ids" not in source
    for marker in (
        "_FINANCE_LEDGER_ID",
        "_QUANT_TRADING_ID",
        "_PQRSD_ASSISTANT_ID",
        "_MARKET_WORKER_IDS",
        "_PLOT_WORKER_IDS",
    ):
        assert marker not in source


def test_factory_has_no_inline_github_workflow() -> None:
    assert not Path("packages/agents/src/duckclaw/github/workflow.py").exists()

    source = _factory_source()
    names = _factory_function_names()
    assert not any(name.startswith("_github_") for name in names)
    assert "_user_requests_github_pr" not in names
    assert "_user_requests_github_pr_retry" not in names

    forbidden = {
        "duckclaw.github." + "workflow",
        "_github_try_deterministic_pr_workflow",
        "_github_pr_workflow_resolved_intent",
        "_github_needs_create_pr_after_push",
        '"github_pr_workflow"',
        "repositorio DuckClaw",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)
    assert leaked == []


def test_factory_has_no_job_hunter_vertical_policy() -> None:
    source = _factory_source()
    names = _factory_function_names()

    forbidden = {
        "_spec_is_job_hunter",
        "duckclaw.egress." + "job_hunter_output_validator",
        "job_hunter_user_requests_job_search",
        "job_hunter_reply_should_block",
        "job_hunter_blocked_reply_message",
        "spec_is_job_hunter",
        "Job-Hunter",
        "jobhunter",
        "job_opportunity_tracking",
        "SEGUIMIENTO DE VACANTE",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert "_spec_is_job_hunter" not in names
    assert leaked == []


def test_factory_has_no_inline_quant_policy() -> None:
    assert not Path("packages/agents/src/duckclaw/quant/runtime_policy.py").exists()
    assert not Path("packages/agents/src/duckclaw/finance/runtime_policy.py").exists()

    names = _factory_function_names()
    leaked = {
        name
        for name in names
        if name.startswith("_quant_")
    }
    assert leaked == set()


def test_factory_does_not_register_broker_or_quant_vertical_bridges() -> None:
    source = _factory_source()
    forbidden = {
        "duckclaw.forge.skills.ibkr_bridge",
        "register_ibkr_skill",
        "replace_get_ibkr_portfolio_with_finanz_live_variant",
        "duckclaw.forge.skills.quant_market_bridge",
        "register_quant_market_skill",
        "duckclaw.forge.skills.quant_trade_bridge",
        "register_quant_trade_skills",
        "duckclaw.forge.skills.quant_cfd_bridge",
        "register_quant_cfd_skill",
        "duckclaw.forge.skills.quant_trader_bridge",
        "register_quant_trader_skills",
        "quant_trading_session_prompt_block",
        "_sync_finanz_lake_beliefs",
    }

    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_factory_has_no_quant_ibkr_finance_deterministic_orchestration() -> None:
    source = _factory_source()
    source_lower = source.lower()
    forbidden = {
        "duckclaw.quant.runtime_policy",
        "duckclaw.finance.runtime_policy",
        "duckclaw.forge.skills.quant_tool_context",
        "finance_ledger",
        "quant_trading",
        "portfolio_live_bridge",
        "ibkr_enabled",
        "get_ibkr_portfolio",
        "fetch_ib_gateway_ohlcv",
        "propose_trade_signal",
        "execute_approved_signal",
        "cancel_trade_signal",
        "evaluate_cfd_state",
        "inspect_macro_pgq",
        "quant_pipeline_context",
        "quant_ohlcv_moc",
        "quant_pipeline_deterministic",
        "quant_autoexec",
    }

    leaked = sorted(marker for marker in forbidden if marker in source)
    broad_vertical_leaks = sorted(
        marker
        for marker in (
            "ibkr",
            "finanz",
            "finance",
            "quant",
            "trader",
            "ticker",
            "broker",
        )
        if marker in source_lower
    )

    assert leaked == []
    assert broad_vertical_leaks == []


def test_factory_delegates_tool_invocation_policy() -> None:
    assert Path("packages/agents/src/duckclaw/workers/tool_invocation_policy.py").exists()

    source = _factory_source()
    names = _factory_function_names()
    assert "ToolInvocationDecision" not in source
    assert "finance_ledger.read_sql" not in source
    assert "market_data_bridge.fetch_market_data" not in source
    assert "decide_db_first_tool_invocation" not in names
    assert "decide_market_data_tool_invocation" not in names


def test_tool_invocation_policy_has_no_vertical_runtime_imports() -> None:
    source = Path("packages/agents/src/duckclaw/workers/tool_invocation_policy.py").read_text(
        encoding="utf-8"
    )
    forbidden = {
        "duckclaw.finance.runtime_policy",
        "finanz",
        "finance_ledger",
        "quant_trading",
        "ibkr",
        "ib_gateway",
        "fetch_ib_gateway_ohlcv",
    }
    leaked = sorted(marker for marker in forbidden if marker in source.lower())
    assert leaked == []


def test_factory_delegates_configured_skill_tool_registration() -> None:
    registry = importlib.import_module("duckclaw.workers.skill_tool_registry")
    from duckclaw.workers import factory

    assert factory._register_pre_llm_skill_tools is registry.register_pre_llm_skill_tools
    assert factory._register_post_llm_skill_tools is registry.register_post_llm_skill_tools
    assert factory._read_visual_artifact_image_as_b64 is registry.read_visual_artifact_image_as_b64
    assert (
        factory._register_pre_llm_skill_tools.__module__
        == "duckclaw.workers.skill_tool_registry"
    )
    assert (
        factory._register_post_llm_skill_tools.__module__
        == "duckclaw.workers.skill_tool_registry"
    )
    assert (
        factory._read_visual_artifact_image_as_b64.__module__
        == "duckclaw.workers.skill_tool_registry"
    )

    source = _factory_source()
    forbidden_bridge_imports = {
        "duckclaw.forge.skills.google_trends_bridge",
        "duckclaw.forge.skills.reddit_bridge",
        "duckclaw.forge.skills.research_bridge",
        "duckclaw.forge.skills.openweather_bridge",
        "duckclaw.forge.skills.tailscale_bridge",
        "duckclaw.forge.skills.fmp_bridge",
        "duckclaw.forge.skills.comfyui_bridge",
        "register_google_trends_skill",
        "register_reddit_skill",
        "register_research_skill",
        "register_openweather_skill",
        "register_tailscale_skill",
        "register_fmp_skill",
        "register_comfyui_skill",
    }
    leaked = sorted(marker for marker in forbidden_bridge_imports if marker in source)
    assert leaked == []


def test_skill_tool_registry_has_no_per_skill_registration_branches() -> None:
    path = Path("packages/agents/src/duckclaw/workers/skill_tool_registry.py")
    source = path.read_text(encoding="utf-8")
    names = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "SkillToolRegistrar" in source
    assert "DEFAULT_SKILL_TOOL_REGISTRY" in source
    forbidden_functions = {
        "_register_google_trends",
        "_register_reddit",
        "_register_research",
        "_register_openweather",
        "_register_tailscale",
        "_register_comfyui",
    }
    assert names.isdisjoint(forbidden_functions)


def test_factory_deprecated_debug_probe_removed() -> None:
    source = _factory_source()
    assert "_ibkr_cancel_debug_log" not in source
    assert "debug-fd1dbb.log" not in source
    assert "hypothesis_id" not in source


def test_factory_facade_stays_thin() -> None:
    """factory.py is a re-export facade; graph assembly lives in sibling modules."""
    line_count = len(_factory_source().splitlines())
    assert line_count <= 250, f"factory.py grew to {line_count} lines; keep it a thin facade"
    names = _factory_function_names()
    assert "build_worker_graph" not in names
    assert "_build_worker_tools" not in names
    assert "_resolve_reddit_share_url_to_comments_url" not in names
    assert "_send_sandbox_heartbeat_telegram" not in names


def test_reddit_helpers_own_share_resolution() -> None:
    reddit = importlib.import_module("duckclaw.workers.factory_reddit_helpers")
    from duckclaw.workers import factory

    assert factory._resolve_reddit_share_url_to_comments_url is reddit._resolve_reddit_share_url_to_comments_url
    assert factory.reddit_share_shortlink_fallback_query is reddit.reddit_share_shortlink_fallback_query
    names = _factory_function_names()
    assert "_resolve_reddit_share_url_to_comments_url" not in names
    assert "reddit_share_shortlink_fallback_query" not in names


def test_agent_node_helpers_own_cancel_and_llm_failure() -> None:
    helpers = importlib.import_module("duckclaw.workers.factory_agent_node_helpers")
    from duckclaw.workers import factory

    assert factory._parse_comfyui_edit_inbound is helpers._parse_comfyui_edit_inbound
    assert factory._agent_node_llm_failure_user_message is helpers._agent_node_llm_failure_user_message
    assert factory._identity_fields is helpers._identity_fields
    names = _factory_function_names()
    assert "_parse_comfyui_edit_inbound" not in names
    assert "_agent_node_llm_failure_user_message" not in names


def test_sandbox_notify_owns_heartbeat_scheduling() -> None:
    notify = importlib.import_module("duckclaw.workers.factory_sandbox_notify")
    from duckclaw.workers import factory

    assert factory._schedule_run_browser_novnc_tool_heartbeat is notify._schedule_run_browser_novnc_tool_heartbeat
    assert factory._send_sandbox_heartbeat_telegram is notify._send_sandbox_heartbeat_telegram
    names = _factory_function_names()
    assert "_schedule_run_browser_novnc_tool_heartbeat" not in names


def test_tool_builder_owns_worker_tools() -> None:
    builder = importlib.import_module("duckclaw.workers.factory_tool_builder")
    from duckclaw.workers import factory

    assert factory._build_worker_tools is builder._build_worker_tools
    assert factory._ensure_worker_duckdb_extensions is builder._ensure_worker_duckdb_extensions
    names = _factory_function_names()
    assert "_build_worker_tools" not in names


def test_graph_builder_modules_respect_line_limits() -> None:
    """factory_graph_* modules stay under modular size guardrails."""
    workers = Path("packages/agents/src/duckclaw/workers")
    limits = {
        "factory_graph_assembly.py": 200,
        "factory_graph_nodes_agent_invoke.py": 450,
    }
    default_max = 400
    for path in sorted(workers.glob("factory_graph_*.py")):
        if path.name == "factory_graph_builder.py":
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        max_lines = limits.get(path.name, default_max)
        assert line_count <= max_lines, f"{path.name} has {line_count} lines (max {max_lines})"


def test_graph_builder_owns_build_worker_graph() -> None:
    graph = importlib.import_module("duckclaw.workers.factory_graph_builder")
    from duckclaw.workers import factory

    assert factory.build_worker_graph is graph.build_worker_graph
    assert factory.build_worker_graph.__module__ == "duckclaw.workers.factory_graph_builder"
    names = _factory_function_names()
    assert "build_worker_graph" not in names


def test_build_worker_graph_compiles_core_nodes_without_external_io(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_builder import build_worker_graph

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    graph = build_worker_graph(
        "default",
        ":memory:",
        None,
        templates_root=templates_root,
        llm_provider="none_llm",
    )

    assert hasattr(graph, "invoke")
    node_names = set(graph.nodes)
    assert {"prepare", "agent", "tools", "set_reply"}.issubset(node_names)
    assert graph._worker_spec is not None
    assert graph._worker_db is not None


def test_build_worker_graph_prepare_agent_set_reply_path_without_llm(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_builder import build_worker_graph

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    graph = build_worker_graph(
        "default",
        ":memory:",
        None,
        templates_root=templates_root,
        llm_provider="none_llm",
    )

    out = graph.invoke(
        {
            "incoming": "hola contrato",
            "chat_id": "chat-smoke",
            "tenant_id": "default",
        }
    )

    assert out.get("reply") == "Sin LLM configurado. Configura DUCKCLAW_LLM_PROVIDER."
    messages = out.get("messages") or []
    assert any(isinstance(m, SystemMessage) for m in messages)
    assert any(isinstance(m, HumanMessage) for m in messages)
    assert any(isinstance(m, AIMessage) for m in messages)


def test_build_worker_graph_invoke_with_fake_llm_reaches_set_reply(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_builder import build_worker_graph

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    graph = build_worker_graph(
        "default",
        ":memory:",
        _FakeBindableLLM(content="respuesta contrato"),
        templates_root=templates_root,
        llm_provider="none_llm",
    )

    out = graph.invoke(
        {
            "incoming": "ping contrato",
            "chat_id": "chat-smoke-llm",
            "tenant_id": "default",
        }
    )

    assert out.get("reply") == "respuesta contrato"


def test_should_continue_routes_tools_and_set_reply() -> None:
    from duckclaw.workers.factory_graph_context import WorkerGraphContext
    from duckclaw.workers.factory_graph_nodes_routing import make_should_continue

    ctx = WorkerGraphContext()
    should_continue = make_should_continue(ctx)

    with_tools = {"messages": [AIMessage(content="", tool_calls=[{"name": "get_current_time", "args": {}, "id": "1"}])]}
    without_tools = {"messages": [AIMessage(content="solo texto")]}

    assert should_continue(with_tools) == "tools"
    assert should_continue(without_tools) == "end"


def test_should_continue_caps_tool_rounds_at_max() -> None:
    from duckclaw.workers.factory_graph_context import WorkerGraphContext
    from duckclaw.workers.factory_graph_nodes_routing import make_should_continue

    ctx = WorkerGraphContext(max_tool_rounds=2)
    should_continue = make_should_continue(ctx)

    capped = {
        "messages": [AIMessage(content="", tool_calls=[{"name": "read_sql", "args": {}, "id": "1"}])],
        "_tool_round": 2,
    }
    assert should_continue(capped) == "end"


def test_build_worker_graph_caps_tool_loop_without_recursion_error(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_builder import build_worker_graph

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    graph = build_worker_graph(
        "default",
        ":memory:",
        _AlwaysToolCallLLM(),
        templates_root=templates_root,
        llm_provider="none_llm",
        max_tool_rounds=2,
    )

    out = graph.invoke(
        {
            "incoming": "loop contrato",
            "chat_id": "chat-tool-cap",
            "tenant_id": "default",
        }
    )

    assert isinstance(out, dict)
    assert "reply" in out
    assert int(out.get("_tool_round") or 0) == 2
    assert (out.get("reply") or "").strip()
    assert "herramienta" in (out.get("reply") or "").lower()


def test_set_reply_synthesizes_reply_when_tool_cap_exhausted(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_builder import build_worker_graph

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    graph = build_worker_graph(
        "default",
        ":memory:",
        _AlwaysToolCallLLM(),
        templates_root=templates_root,
        llm_provider="none_llm",
        max_tool_rounds=1,
    )

    out = graph.invoke(
        {
            "incoming": "cap inmediato",
            "chat_id": "chat-tool-cap-1",
            "tenant_id": "default",
        }
    )

    assert (out.get("reply") or "").strip()
    assert "herramienta" in (out.get("reply") or "").lower()
    last_msg = (out.get("messages") or [])[-1]
    assert not getattr(last_msg, "tool_calls", None)


def test_prepare_node_feeds_agent_with_system_and_human_messages(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context
    from duckclaw.workers.factory_graph_nodes_prepare import make_prepare_node

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    ctx = initialize_worker_graph_context(
        "default",
        ":memory:",
        None,
        templates_root=templates_root,
        llm_provider="none_llm",
    )
    ctx.sandbox_enabled_for_state = lambda _state: False
    prepare_node = make_prepare_node(ctx)

    out = prepare_node({"incoming": "mensaje prepare", "chat_id": "c-prepare", "tenant_id": "default"})

    assert out.get("incoming") == "mensaje prepare"
    roles = [type(m).__name__ for m in out.get("messages") or []]
    assert roles[0] == "SystemMessage"
    assert "HumanMessage" in roles


def test_tools_node_wires_tool_lookup_from_context(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context
    from duckclaw.workers.factory_graph_nodes_tools import make_tools_node

    templates_root = tmp_path / "layout"
    _write_default_worker_layout(templates_root)
    ctx = initialize_worker_graph_context(
        "default",
        ":memory:",
        None,
        templates_root=templates_root,
        llm_provider="none_llm",
    )
    ctx.sandbox_enabled_for_state = lambda _state: True

    captured: dict[str, Any] = {}

    class _EchoTool:
        name = "echo_tool"

        def invoke(self, args: dict[str, Any]) -> str:
            captured["args"] = args
            return "tool-ok"

    ctx.tools_by_name = {"echo_tool": _EchoTool()}
    ctx.tools_by_name_sandbox_off = {"echo_tool": _EchoTool()}
    tools_node = make_tools_node(ctx)

    state = {
        "messages": [
            SystemMessage(content="sys"),
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[{"name": "echo_tool", "args": {"q": "x"}, "id": "tc1"}],
            ),
        ],
        "chat_id": "chat-tools",
        "tenant_id": "default",
    }
    out = tools_node(state)

    assert captured.get("args") == {"q": "x"}
    assert any(isinstance(m, ToolMessage) for m in out.get("messages") or [])


def test_manifest_agent_node_max_tool_rounds_applied_to_context(tmp_path: Path) -> None:
    from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context

    templates_root = tmp_path / "layout"
    worker_dir = templates_root / "templates" / "workers" / "default"
    worker_dir.mkdir(parents=True, exist_ok=True)
    worker_dir.joinpath("manifest.yaml").write_text(
        "name: smoke-default\nid: default\ntopology: general\nskills: []\n"
        "agent_node:\n  max_tool_rounds: 20\n",
        encoding="utf-8",
    )
    worker_dir.joinpath("system_prompt.md").write_text("Eres un agente de prueba.", encoding="utf-8")

    ctx = initialize_worker_graph_context(
        "default",
        ":memory:",
        None,
        templates_root=templates_root,
        llm_provider="none_llm",
    )
    assert ctx.max_tool_rounds == 20


def test_first_bindable_tool_skips_sandbox_already_in_ran() -> None:
    from duckclaw.workers.tool_orchestration import _first_bindable_tool

    tools_by_name = {"execute_sandbox_script": object(), "run_sandbox": object()}
    ran = {"execute_sandbox_script", "read_sql"}
    assert _first_bindable_tool(
        ["execute_sandbox_script", "run_sandbox"],
        tools_by_name,
        ran,
    ) == "run_sandbox"
    ran_with_both = {"execute_sandbox_script", "run_sandbox", "read_sql"}
    assert (
        _first_bindable_tool(
            ["execute_sandbox_script", "run_sandbox"],
            tools_by_name,
            ran_with_both,
        )
        is None
    )
