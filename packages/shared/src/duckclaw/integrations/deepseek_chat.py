"""DeepSeek thinking mode keeps reasoning_content on an open tool turn."""

from __future__ import annotations

from typing import Any

import httpx
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI


class DeepSeekChatOpenAI(ChatOpenAI):
    """Send reasoning_content on the wire. The OpenAI SDK drops that field."""

    def _generate(self, messages: list[Any], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> Any:
        del run_manager
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        return self._create_chat_result(_post_chat_completions(self, payload))

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outbound = payload.get("messages")
        if isinstance(outbound, list):
            _attach_open_reasoning(self._convert_input(input_).to_messages(), outbound)
        return payload

    def _create_chat_result(self, response: Any, generation_info: dict | None = None) -> Any:
        result = super()._create_chat_result(response, generation_info)
        _stash_reasoning_content(response, result)
        return result


def _api_key(llm: DeepSeekChatOpenAI) -> str:
    key = llm.openai_api_key
    if hasattr(key, "get_secret_value"):
        return str(key.get_secret_value() or "")
    return str(key or "")


def _completions_url(llm: DeepSeekChatOpenAI) -> str:
    base = str(llm.openai_api_base or "https://api.deepseek.com/v1").rstrip("/")
    return f"{base}/chat/completions"


def _request_body(payload: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in payload.items() if key != "extra_body"}
    extra = payload.get("extra_body")
    if isinstance(extra, dict):
        body.update(extra)
    body.pop("stream", None)
    return body


def _post_chat_completions(llm: DeepSeekChatOpenAI, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        _completions_url(llm),
        headers={"Authorization": f"Bearer {_api_key(llm)}"},
        json=_request_body(payload),
        timeout=llm.request_timeout or 60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Error code: {response.status_code} - {response.text}")
    return response.json()


def _response_choices(response: Any) -> list[dict[str, Any]]:
    raw = response if isinstance(response, dict) else response.model_dump()
    choices = raw.get("choices") or []
    return [choice for choice in choices if isinstance(choice, dict)]


def _stash_reasoning_content(response: Any, result: Any) -> None:
    for generation, choice in zip(result.generations, _response_choices(response)):
        message = choice.get("message") or {}
        reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
        if reasoning and isinstance(generation.message, AIMessage):
            generation.message.additional_kwargs["reasoning_content"] = reasoning


def _attach_open_reasoning(lc_messages: list[Any], outbound: list[dict[str, Any]]) -> None:
    """DeepSeek exige reasoning_content en el turno de tools y lo rechaza después."""
    last_user = max(
        (index for index, item in enumerate(outbound) if item.get("role") in ("user", "human")),
        default=-1,
    )
    assistants = [message for message in lc_messages if isinstance(message, AIMessage)]
    assistant_index = 0
    for index, item in enumerate(outbound):
        if item.get("role") != "assistant":
            continue
        source = assistants[assistant_index] if assistant_index < len(assistants) else None
        assistant_index += 1
        if source is None or index < last_user:
            continue
        reasoning = source.additional_kwargs.get("reasoning_content")
        if reasoning:
            item["reasoning_content"] = reasoning
