"""Alineación traza SFT con egress cuando la tool va como JSON en content."""

from duckclaw.graphs.conversation_traces import align_trace_messages_with_assistant_egress


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
