from __future__ import annotations

import importlib
from types import SimpleNamespace


def _runtime_policy(*names: str):
    from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy

    capabilities = tuple(
        WorkerCapability(
            capability_id=f"cap_{name}",
            name=name,
            kind="runtime_policy",
            provider="duckclaw",
            permission="use",
            config={},
            policy={},
            quota={},
        )
        for name in names
    )
    return WorkerRuntimePolicy(
        worker_id="worker_alpha",
        identity=None,
        capabilities=capabilities,
    )


def _spec_with_capabilities(*names: str):
    return SimpleNamespace(runtime_policy=_runtime_policy(*names))


def test_local_ledger_read_sql_depends_on_runtime_policy_and_available_tool() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="Resumen de registros locales en DuckDB",
        available_tools={"read_sql", "admin_sql"},
    )

    assert decision.tool_name == "read_sql"
    assert decision.reason == "local_ledger.read_sql.local_data"
    assert not decision.requires_heuristic_first_tool

    missing_capability = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("market_data_bridge"),
        incoming="Resumen de registros locales en DuckDB",
        available_tools={"read_sql", "admin_sql"},
    )
    assert not missing_capability.should_force

    missing_tool = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="Resumen de registros locales en DuckDB",
        available_tools={"admin_sql"},
    )
    assert not missing_tool.should_force


def test_local_ledger_admin_sql_write_decision_is_explicit() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="Actualiza el registro id=3 en la tabla items en DuckDB",
        available_tools={"read_sql", "admin_sql"},
    )

    assert decision.tool_name == "admin_sql"
    assert decision.reason == "local_ledger.admin_sql.local_record_write"
    assert decision.requires_heuristic_first_tool


def test_local_ledger_current_time_decision_is_direct_tool_call_once_per_turn() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="Resumen de registros locales en DuckDB",
        available_tools={"get_current_time", "read_sql"},
        called_tools_since_last_human=set(),
    )

    assert decision.tool_name == "get_current_time"
    assert decision.direct_tool_call
    assert decision.tool_args == {}
    assert decision.reason == "clock_anchor.get_current_time"

    already_called = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="Resumen de registros locales en DuckDB",
        available_tools={"get_current_time", "read_sql"},
        called_tools_since_last_human={"get_current_time"},
    )
    assert not already_called.should_force


def test_current_time_forced_without_local_ledger_or_time_keywords() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities("market_data_bridge"),
        incoming="Ya lo corrí",
        available_tools={"get_current_time", "read_sql"},
        called_tools_since_last_human=set(),
    )
    assert decision.tool_name == "get_current_time"
    assert decision.direct_tool_call
    assert decision.reason == "clock_anchor.get_current_time"

    system_event = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities(),
        incoming="[system_event: heartbeat]",
        available_tools={"get_current_time"},
        called_tools_since_last_human=set(),
    )
    assert not system_event.should_force

    missing_tool = policy.decide_current_time_tool_invocation(
        spec=_spec_with_capabilities(),
        incoming="Qué hora es?",
        available_tools={"read_sql"},
        called_tools_since_last_human=set(),
    )
    assert not missing_tool.should_force


def test_email_intent_skips_db_first_read_sql() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming=(
            "busca el correo y saca insights\n\n"
            "[EMAIL_SCREENSHOT] Usuario adjuntó captura de UN correo.\n"
            "Contexto visual adjunto: Remitente: Data Points."
        ),
        available_tools={"read_sql", "admin_sql"},
    )
    assert not decision.should_force

    marker_only = policy.decide_db_first_tool_invocation(
        spec=_spec_with_capabilities("local_ledger"),
        incoming="[DIRECTIVA_CORREO] Pide correo concreto. Usa Gmail MCP.",
        available_tools={"read_sql", "admin_sql"},
    )
    assert not marker_only.should_force


def test_loop_system_event_forces_evaluate_homeostasis_first_hop() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    loop_msg = (
        "[SYSTEM_EVENT: Ciclo de auto-mejora programado /loop. Metas (/goals): SL XLU. "
        "1) Preferí evaluate_homeostasis si tu worker la expone (TP/SL, OCA, OHLCV); "
        "assess_crons_alignment solo cubre metas /goals.]"
    )
    decision = policy.decide_loop_homeostasis_tool_invocation(
        incoming=loop_msg,
        available_tools={"read_sql", "evaluate_homeostasis", "assess_crons_alignment"},
    )
    assert decision.tool_name == "evaluate_homeostasis"
    assert decision.reason == "platform.loop.evaluate_homeostasis.first_hop"
    assert not decision.requires_heuristic_first_tool

    already = policy.decide_loop_homeostasis_tool_invocation(
        incoming=loop_msg,
        available_tools={"evaluate_homeostasis"},
        already_has_tool_result=True,
    )
    assert not already.should_force

    called = policy.decide_loop_homeostasis_tool_invocation(
        incoming=loop_msg,
        available_tools={"evaluate_homeostasis"},
        called_tools_since_last_human={"evaluate_homeostasis"},
    )
    assert not called.should_force

    missing = policy.decide_loop_homeostasis_tool_invocation(
        incoming=loop_msg,
        available_tools={"read_sql", "assess_crons_alignment"},
    )
    assert not missing.should_force

    ordinary = policy.decide_loop_homeostasis_tool_invocation(
        incoming="¿cómo está el portfolio?",
        available_tools={"evaluate_homeostasis"},
    )
    assert not ordinary.should_force

    # Plain SYSTEM_EVENT without loop/proactive markers must not force.
    unrelated_event = policy.decide_loop_homeostasis_tool_invocation(
        incoming="[SYSTEM_EVENT: heartbeat ping]",
        available_tools={"evaluate_homeostasis"},
    )
    assert not unrelated_event.should_force


def test_update_system_prompt_forced_on_persist_request() -> None:
    policy = importlib.import_module("duckclaw.workers.tool_invocation_policy")

    decision = policy.decide_update_system_prompt_invocation(
        incoming="guardalo en tu prompt",
        available_tools={"read_sql", "update_system_prompt"},
    )
    assert decision.tool_name == "update_system_prompt"
    assert decision.reason == "platform.update_system_prompt.persist_request"

    for phrase in (
        "ajusta tu prompt",
        "actualiza tu prompt",
        "mejora tu prompt",
        "modifica tu prompt",
        "cambia tu system prompt",
        "improve your prompt",
    ):
        forced = policy.decide_update_system_prompt_invocation(
            incoming=phrase,
            available_tools={"update_system_prompt"},
        )
        assert forced.tool_name == "update_system_prompt", phrase

    named = policy.decide_update_system_prompt_invocation(
        incoming="no usaste update_system_prompt",
        available_tools={"update_system_prompt"},
    )
    assert named.tool_name == "update_system_prompt"

    already = policy.decide_update_system_prompt_invocation(
        incoming="guardalo en tu prompt",
        available_tools={"update_system_prompt"},
        called_tools_since_last_human={"update_system_prompt"},
    )
    assert not already.should_force

    unrelated = policy.decide_update_system_prompt_invocation(
        incoming="cuánto debo este mes",
        available_tools={"update_system_prompt", "read_sql"},
    )
    assert not unrelated.should_force

    missing = policy.decide_update_system_prompt_invocation(
        incoming="actualiza tu system prompt con mi nombre",
        available_tools={"read_sql"},
    )
    assert not missing.should_force
