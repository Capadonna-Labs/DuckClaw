"""The tool-summary fallback says so when the model hit the output-token cap."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.egress import tool_response_repair as trr


def _msgs(finish_reason: str) -> list:
    return [
        HumanMessage("propón parámetros"),
        AIMessage(content="", tool_calls=[{"name": "read_sql", "args": {"query": "x"}, "id": "c1"}]),
        ToolMessage(content='[{"a": 1}, {"a": 2}]', tool_call_id="c1", name="read_sql"),
        AIMessage(content="", response_metadata={"finish_reason": finish_reason}),
    ]


def test_detects_output_cap() -> None:
    assert trr.last_reply_hit_output_limit(_msgs("length")) is True
    assert trr.last_reply_hit_output_limit(_msgs("stop")) is False


def test_fallback_is_labeled_only_when_truncated(monkeypatch) -> None:
    monkeypatch.setattr(trr, "_repair_tool_response_egress_reply_body", lambda *a, **k: "2 registros.")
    cut = trr.repair_tool_response_egress_reply(None, object(), "propón", "", _msgs("length"))
    assert cut.startswith("⚠️ La respuesta del modelo se cortó") and cut.endswith("2 registros.")
    ok = trr.repair_tool_response_egress_reply(None, object(), "propón", "", _msgs("stop"))
    assert ok == "2 registros."
