from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from duckclaw.workers.context_monitor import (
    build_context_monitor_node,
    compose_context_summary_prompt,
    llm_fold_conversation_summary,
)


class _FakeSummaryLLM:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    def invoke(self, messages: list[object]) -> object:
        self.calls.append(messages)
        return type("Reply", (), {"content": "Resumen nuevo"})()


def test_compose_context_summary_prompt_is_generic_plain_text() -> None:
    prompt = compose_context_summary_prompt("Sistema base", "Decisiones previas")

    assert prompt == "Sistema base\n\nResumen compactado del hilo:\nDecisiones previas"
    assert "BI" not in prompt
    assert "##" not in prompt


def test_llm_fold_conversation_summary_uses_generic_compression_prompt() -> None:
    llm = _FakeSummaryLLM()

    summary = llm_fold_conversation_summary(
        llm,
        [
            HumanMessage(content="Necesito comparar errores por servicio."),
            ToolMessage(content="x" * 2000, tool_call_id="tool-1", name="read_sql"),
        ],
        "Previo",
    )

    assert summary == "Resumen nuevo"
    system_prompt = str(getattr(llm.calls[0][0], "content", ""))
    assert "compresión de contexto" in system_prompt
    assert "analista BI" not in system_prompt
    human_prompt = str(getattr(llm.calls[0][1], "content", ""))
    assert "Previo" in human_prompt
    assert "tool_read_sql" in human_prompt


def test_context_monitor_node_compacts_any_worker_with_enabled_policy() -> None:
    llm = _FakeSummaryLLM()
    node = build_context_monitor_node(
        pruning_config={
            "enabled": True,
            "max_messages": 3,
            "max_estimated_tokens": 500,
            "keep_last_messages": 1,
            "tool_content_max_chars": 50,
        },
        prompt_base="Sistema base",
        llm_summary=llm,
        identity_fields=lambda state: {"chat_id": state["chat_id"]},
    )
    state = {
        "chat_id": "chat-1",
        "messages": [
            SystemMessage(content="Sistema base"),
            HumanMessage(content="antiguo"),
            ToolMessage(content="t" * 200, tool_call_id="tool-1", name="read_sql"),
            HumanMessage(content="reciente"),
        ],
    }

    out = node(state)

    assert out["chat_id"] == "chat-1"
    assert out["analytical_summary"] == "Resumen nuevo"
    assert len(out["messages"]) == 2
    assert isinstance(out["messages"][0], SystemMessage)
    assert "Resumen compactado del hilo:\nResumen nuevo" in str(out["messages"][0].content)
    assert out["messages"][-1].content == "reciente"
