from __future__ import annotations

import duckdb
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from duckclaw.workers.provider_input_budget import (
    apply_provider_input_budget,
    configure_provider_budget_runtime_db_provider,
    context_prune_globally_enabled,
    context_prune_max_estimated_tokens,
    estimate_tokens_from_messages,
    groq_max_estimated_input_tokens,
    groq_tool_message_max_chars,
    mlx_max_estimated_input_tokens,
    mlx_tool_message_max_chars,
    mlx_effective_message_cap,
    mlx_max_bound_tools,
    normalized_context_pruning,
    split_for_pruning,
)


class _DuckDbAdapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_normalized_context_pruning_default_on_without_manifest(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", raising=False)
    spec = SimpleNamespace(context_pruning_config=None)

    out = normalized_context_pruning(spec)

    assert out.get("enabled") is True
    assert out["max_estimated_tokens"] == 4_000_000
    assert out["max_messages"] >= 10_000


def test_normalized_context_pruning_respects_max_tokens_m_env(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M", "2")
    spec = SimpleNamespace(context_pruning_config={})

    out = normalized_context_pruning(spec)

    assert out["max_estimated_tokens"] == 2_000_000


def test_normalized_context_pruning_global_off(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", "0")
    spec = SimpleNamespace(context_pruning_config={"enabled": True})

    assert normalized_context_pruning(spec) == {}


def test_normalized_context_pruning_manifest_opt_out() -> None:
    spec = SimpleNamespace(context_pruning_config={"enabled": False})

    assert normalized_context_pruning(spec) == {}


def test_context_prune_max_estimated_tokens_clamps(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M", "100")
    assert context_prune_max_estimated_tokens() == 32_000_000
    monkeypatch.setenv("DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M", "0.1")
    assert context_prune_max_estimated_tokens() == 500_000


def test_context_prune_globally_enabled_default(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", raising=False)
    assert context_prune_globally_enabled() is True


def test_normalized_context_pruning_clamps_config_values() -> None:
    spec = SimpleNamespace(
        context_pruning_config={
            "enabled": True,
            "max_messages": 1,
            "max_estimated_tokens": 10,
            "keep_last_messages": 0,
            "tool_content_max_chars": 10,
            "sandbox_heartbeat": False,
        }
    )

    out = normalized_context_pruning(spec)

    assert out == {
        "enabled": True,
        "max_messages": 2,
        "max_estimated_tokens": 500,
        "keep_last_messages": 1,
        "tool_content_max_chars": 500,
        "sandbox_heartbeat": False,
    }


def test_provider_input_budget_uses_tool_truncation_and_preserves_recent_context(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DUCKCLAW_GROQ_MAX_INPUT_TOKENS", "1500")
    monkeypatch.setenv("DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS", "400")
    messages = [
        SystemMessage(content="system " + "s" * 1000),
        HumanMessage(content="old " + "x" * 6000),
        ToolMessage(content="tool " + "t" * 2000, tool_call_id="tool-1", name="read_sql"),
        HumanMessage(content="recent question"),
    ]

    out = apply_provider_input_budget(messages, provider="groq")

    assert isinstance(out[0], SystemMessage)
    assert out[-1].content == "recent question"
    assert all(getattr(message, "content", "") != messages[1].content for message in out)
    assert estimate_tokens_from_messages(out) <= 1500
    tool_messages = [message for message in out if isinstance(message, ToolMessage)]
    assert tool_messages
    assert str(tool_messages[0].content).endswith("\n…[truncado por tamaño]")


def test_provider_budget_runtime_settings_override_legacy_env(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_GROQ_MAX_INPUT_TOKENS", "9000")
    monkeypatch.setenv("DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS", "9000")
    monkeypatch.setenv("DUCKCLAW_MLX_MAX_INPUT_TOKENS", "9000")
    monkeypatch.setenv("DUCKCLAW_MLX_TOOL_MESSAGE_MAX_CHARS", "9000")

    from duckclaw.admin_runtime_settings import upsert_runtime_setting

    con = duckdb.connect(":memory:")
    try:
        db = _DuckDbAdapter(con)
        upsert_runtime_setting(
            db,
            tenant_id="global",
            actor_email="",
            domain="runtime.provider_budget",
            key="groq.max_input_tokens",
            value_text="1800",
            value_kind="integer",
            updated_by="test",
        )
        upsert_runtime_setting(
            db,
            tenant_id="global",
            actor_email="",
            domain="runtime.provider_budget",
            key="groq.tool_message_max_chars",
            value_text="450",
            value_kind="integer",
            updated_by="test",
        )
        upsert_runtime_setting(
            db,
            tenant_id="global",
            actor_email="",
            domain="runtime.provider_budget",
            key="mlx.max_input_tokens",
            value_text="2600",
            value_kind="integer",
            updated_by="test",
        )
        upsert_runtime_setting(
            db,
            tenant_id="global",
            actor_email="",
            domain="runtime.provider_budget",
            key="mlx.tool_message_max_chars",
            value_text="650",
            value_kind="integer",
            updated_by="test",
        )
        configure_provider_budget_runtime_db_provider(lambda: db)

        assert groq_max_estimated_input_tokens() == 1800
        assert groq_tool_message_max_chars() == 450
        assert mlx_max_estimated_input_tokens() == 2600
        assert mlx_tool_message_max_chars() == 650
    finally:
        configure_provider_budget_runtime_db_provider(None)
        con.close()


def test_provider_budget_uses_legacy_env_only_without_runtime_setting(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_GROQ_MAX_INPUT_TOKENS", "1700")
    configure_provider_budget_runtime_db_provider(None)

    assert groq_max_estimated_input_tokens() == 1700


def test_split_for_pruning_keeps_ai_tool_call_with_following_tool_result() -> None:
    ai_with_tool = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_sql", "args": {}}],
    )
    tool_result = ToolMessage(content="result", tool_call_id="call-1", name="read_sql")
    non_system = [
        HumanMessage(content="old"),
        ai_with_tool,
        tool_result,
    ]

    head, tail = split_for_pruning(non_system, keep_last=1)

    assert head == [non_system[0]]
    assert tail == [ai_with_tool, tool_result]


def test_mlx_max_estimated_input_tokens_default_20k(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MLX_MAX_INPUT_TOKENS", raising=False)
    configure_provider_budget_runtime_db_provider(None)

    assert mlx_max_estimated_input_tokens() == 20_000


def test_normalized_context_pruning_mlx_uses_20k_threshold(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MLX_MAX_INPUT_TOKENS", raising=False)
    spec = SimpleNamespace(context_pruning_config=None)

    out = normalized_context_pruning(spec, provider="mlx")

    assert out.get("enabled") is True
    assert out["max_estimated_tokens"] == 20_000


def test_normalized_context_pruning_openrouter_keeps_global_threshold(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M", raising=False)
    spec = SimpleNamespace(context_pruning_config=None)

    out = normalized_context_pruning(spec, provider="openrouter")

    assert out["max_estimated_tokens"] == 4_000_000


def test_mlx_provider_input_budget_trims_large_history(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MLX_MAX_INPUT_TOKENS", raising=False)
    messages = [
        SystemMessage(content="system " + "s" * 2000),
        HumanMessage(content="old " + "x" * 120_000),
        HumanMessage(content="recent question"),
    ]

    out = apply_provider_input_budget(messages, provider="mlx")

    assert out[-1].content == "recent question"
    assert estimate_tokens_from_messages(out) <= 20_000


def test_mlx_max_bound_tools_default(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MLX_MAX_INPUT_TOKENS", raising=False)
    configure_provider_budget_runtime_db_provider(None)

    assert mlx_max_bound_tools() == 45


def test_mlx_effective_message_cap_reserves_tool_headroom() -> None:
    configure_provider_budget_runtime_db_provider(None)
    assert mlx_effective_message_cap(bound_tools_n=45) == 4250
    assert mlx_effective_message_cap(bound_tools_n=0) == 20_000


def test_mlx_tools_for_bind_caps_surface() -> None:
    from duckclaw.workers.tool_binding import mlx_tools_for_bind

    tools = [SimpleNamespace(name=f"tool_{i}") for i in range(120)]
    tools[0] = SimpleNamespace(name="read_sql")
    out = mlx_tools_for_bind(tools, max_tools=10)
    assert len(out) == 10
    assert getattr(out[0], "name") == "read_sql"
