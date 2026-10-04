"""DeepSeek thinking mode must echo reasoning_content on an open tool turn."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage

from duckclaw.integrations.deepseek_chat import DeepSeekChatOpenAI


def _tool_response() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "miro la hora y luego el canal",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "get_current_time", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _llm() -> DeepSeekChatOpenAI:
    return DeepSeekChatOpenAI(model="deepseek-v4-flash", api_key="test-key")


def test_tool_turn_echoes_reasoning_content() -> None:
    llm = _llm()
    assistant = llm._create_chat_result(_tool_response()).generations[0].message
    payload = llm._get_request_payload(
        [
            HumanMessage("que sabes del canal"),
            assistant,
            ToolMessage(content="2026-10-04T00:09:00", tool_call_id="call_1"),
        ]
    )
    echoed = [item for item in payload["messages"] if item["role"] == "assistant"]

    assert echoed[0]["reasoning_content"] == "miro la hora y luego el canal"
    assert "thinking" not in payload


def test_reasoning_content_is_dropped_after_the_next_user_turn() -> None:
    llm = _llm()
    assistant = llm._create_chat_result(_tool_response()).generations[0].message
    payload = llm._get_request_payload(
        [
            HumanMessage("que sabes del canal"),
            assistant,
            ToolMessage(content="ok", tool_call_id="call_1"),
            HumanMessage("otra pregunta"),
        ]
    )
    echoed = [item for item in payload["messages"] if item["role"] == "assistant"]

    assert "reasoning_content" not in echoed[0]
    assert "thinking" not in payload


def test_plain_turn_keeps_thinking_enabled() -> None:
    payload = _llm()._get_request_payload([HumanMessage("hola")])

    assert "thinking" not in payload


def test_generate_posts_reasoning_content(monkeypatch) -> None:
    llm = _llm()
    assistant = llm._create_chat_result(_tool_response()).generations[0].message
    captured: dict = {}

    class _Response:
        status_code = 200

        def json(self) -> dict:
            return _tool_response()

    def _post(url: str, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setattr("duckclaw.integrations.deepseek_chat.httpx.post", _post)
    llm._generate(
        [
            HumanMessage("que sabes del canal"),
            assistant,
            ToolMessage(content="2026-10-04T00:09:00", tool_call_id="call_1"),
        ]
    )
    assistant_out = [item for item in captured["json"]["messages"] if item["role"] == "assistant"]

    assert captured["url"].endswith("/chat/completions")
    assert assistant_out[0]["reasoning_content"] == "miro la hora y luego el canal"
    assert "thinking" not in captured["json"]
