from __future__ import annotations

import ast
from pathlib import Path


FACTORY_PATH = Path("packages/agents/src/duckclaw/workers/factory.py")


def _factory_source() -> str:
    return FACTORY_PATH.read_text(encoding="utf-8")


def _factory_function_names() -> set[str]:
    tree = ast.parse(_factory_source())
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


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


def test_factory_has_no_inline_github_workflow() -> None:
    assert Path("packages/agents/src/duckclaw/github/workflow.py").exists()

    names = _factory_function_names()
    assert not any(name.startswith("_github_") for name in names)
    assert "_user_requests_github_pr" not in names
    assert "_user_requests_github_pr_retry" not in names


def test_factory_has_no_inline_quant_policy() -> None:
    assert Path("packages/agents/src/duckclaw/quant/runtime_policy.py").exists()

    names = _factory_function_names()
    allowed_compat_wrappers = {"_quant_strip_duplicate_ibkr_portfolio_tool_calls"}
    leaked = {
        name
        for name in names
        if name.startswith("_quant_") and name not in allowed_compat_wrappers
    }
    assert leaked == set()


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
