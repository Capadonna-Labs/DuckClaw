from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, ToolMessage

from duckclaw.workers.tool_output_truncation import (
    compact_run_sandbox_tool_content_for_llm,
    truncate_tool_messages_for_llm,
)


def test_truncate_tool_messages_limits_plain_tool_content() -> None:
    tool = ToolMessage(content="x" * 20, tool_call_id="plain-1", name="read_sql")

    out = truncate_tool_messages_for_llm([HumanMessage(content="hi"), tool], 8)

    assert len(out) == 2
    assert out[0].content == "hi"
    assert isinstance(out[1], ToolMessage)
    assert out[1].name == "read_sql"
    assert out[1].tool_call_id == "plain-1"
    assert out[1].content == "x" * 8 + "\n…[truncado por tamaño]"


def test_compact_run_sandbox_removes_figure_base64_and_truncates_streams() -> None:
    payload = json.dumps(
        {
            "figure_base64": "A" * 80,
            "stdout": "s" * 4100,
            "stderr": "e" * 10,
            "exit_code": 0,
        }
    )

    out = compact_run_sandbox_tool_content_for_llm(payload, 5000)

    assert "figure_base64" not in out
    data = json.loads(out)
    assert data["exit_code"] == 0
    assert data["stdout"] == "s" * 4000 + "…[truncado]"
    assert data["stderr"] == "e" * 10


def test_truncate_tool_messages_compacts_sandbox_tool_content() -> None:
    payload = json.dumps({"figure_base64": "A" * 80, "output": "ok", "exit_code": 0})
    tool = ToolMessage(content=payload, tool_call_id="sandbox-1", name="run_sandbox")

    out = truncate_tool_messages_for_llm([tool], 200)

    assert len(out) == 1
    assert isinstance(out[0], ToolMessage)
    assert out[0].name == "run_sandbox"
    assert out[0].tool_call_id == "sandbox-1"
    assert "figure_base64" not in str(out[0].content)
    assert '"output": "ok"' in str(out[0].content)


def test_truncate_tool_messages_sanitizes_reddit_tool_json() -> None:
    raw_json = json.dumps(
        {
            "subreddit": "worldnews",
            "posts": [
                {
                    "title": "World event",
                    "score": 42,
                    "permalink": "/r/worldnews/comments/abc/world_event/",
                    "is_self": False,
                }
            ],
        }
    )
    tool = ToolMessage(content=raw_json, tool_call_id="reddit-1", name="reddit_get_subreddit_posts")

    out = truncate_tool_messages_for_llm([tool], 2000)

    body = str(out[0].content)
    assert "World event" in body
    assert '"posts"' not in body
    assert out[0].tool_call_id == "reddit-1"
