from __future__ import annotations

import ast
from pathlib import Path

import pytest


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
    assert Path("packages/agents/src/duckclaw/quant/runtime_policy.py").exists()

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


def test_factory_deprecated_debug_probe_removed() -> None:
    source = _factory_source()
    assert "_ibkr_cancel_debug_log" not in source
    assert "debug-fd1dbb.log" not in source
    assert "hypothesis_id" not in source
