"""Alineación traza SFT con egress cuando la tool va como JSON en content."""

from langchain_core.messages import AIMessage, HumanMessage

from duckclaw.graphs.conversation_traces import (
    align_trace_messages_with_assistant_egress,
    sync_final_assistant_egress_in_langchain_messages,
)


def test_align_trace_replaces_embedded_tool_json_with_egress() -> None:
    msgs: list[dict] = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": '{"name":"read_sql","parameters":{"query":"SELECT 1"}}'},
    ]
    align_trace_messages_with_assistant_egress(msgs, '[{"id": "1", "name": "Bancolombia"}]')
    assert "read_sql" not in msgs[-1]["content"]
    assert "Bancolombia" in msgs[-1]["content"]


def test_align_trace_skips_when_last_has_tool_calls_shape() -> None:
    msgs: list[dict] = [
        {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": "read_sql", "arguments": "{}"}}]},
    ]
    align_trace_messages_with_assistant_egress(msgs, "solo egress")
    assert msgs[-1].get("tool_calls")


def test_sync_final_assistant_overwrites_raw_model_with_egress() -> None:
    msgs: list = [
        HumanMessage(content="hola"),
        AIMessage(
            content=(
                "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]\n\n"
                "Error de Ingesta: DuckDB esta desconectado."
            )
        ),
    ]
    assert sync_final_assistant_egress_in_langchain_messages(msgs, "Resumen limpio para Telegram.")
    assert msgs[-1].content == "Resumen limpio para Telegram."


def test_sync_final_assistant_noop_when_already_equal() -> None:
    msgs: list = [AIMessage(content="igual")]
    assert not sync_final_assistant_egress_in_langchain_messages(msgs, "igual")


def test_sync_final_assistant_skips_when_tool_calls() -> None:
    msgs: list = [
        AIMessage(
            content="",
            tool_calls=[{"name": "read_sql", "args": {}, "id": "x", "type": "tool_call"}],
        )
    ]
    assert not sync_final_assistant_egress_in_langchain_messages(msgs, "egress only")
