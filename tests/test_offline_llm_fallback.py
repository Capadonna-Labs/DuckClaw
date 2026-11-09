"""The local model answers only when the cloud one is unreachable, with the same tools."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from duckclaw.workers.factory_graph_nodes_agent_invoke import _invoke_offline_fallback


class _Fake:
    def __init__(self, reply: str = "hola", boom: bool = False) -> None:
        self.reply, self.boom, self.bound = reply, boom, None

    def invoke(self, _messages):
        if self.boom:
            raise RuntimeError("local down")
        return AIMessage(content=self.reply)


class _Primary:
    kwargs = {"tools": [{"type": "function", "function": {"name": "read_sql"}}]}


def _bind(llm, tools):
    llm.bound = tools
    return llm


def test_fallback_only_on_connectivity_errors() -> None:
    fb = _Fake()
    got = _invoke_offline_fallback(fb, _bind, _Primary(), [], ConnectionError("Connection refused"), "w")
    assert got is not None and "modelo local" in got.content and fb.bound == _Primary.kwargs["tools"]
    assert _invoke_offline_fallback(fb, _bind, _Primary(), [], ValueError("400 invalid tool schema"), "w") is None
    assert _invoke_offline_fallback(None, _bind, _Primary(), [], ConnectionError("x"), "w") is None
    assert _invoke_offline_fallback(_Fake(boom=True), _bind, _Primary(), [], TimeoutError("timed out"), "w") is None
