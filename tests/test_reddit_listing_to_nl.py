"""format_reddit_mcp_json_to_nl: JSON de mcp-reddit → Markdown legible (duckclaw.utils.formatters)."""

import json

from langchain_core.messages import HumanMessage, ToolMessage

from duckclaw.utils.formatters import (
    REDDIT_MCP_LLM_MAX_POSTS,
    build_reddit_llm_context_block,
    format_reddit_mcp_json_to_nl,
    format_reddit_mcp_reply_if_applicable,
    sanitize_reddit_tool_messages_for_llm,
)


def test_formats_subreddit_posts_json() -> None:
    raw = """finanz 2

{
  "subreddit": "worldnews",
  "sort": "hot",
  "posts": [
    {"id": "1abc", "title": "Hello world", "score": 100, "permalink": "/r/worldnews/comments/1abc/hello/", "is_self": false},
    {"id": "2def", "title": "Otro", "score": 5, "url": "https://example.com/x", "is_self": false}
  ]
}"""
    out = format_reddit_mcp_json_to_nl(raw)
    assert out is not None
    assert "## r/worldnews (Top 2 posts)" in out
    assert "Hello world" in out
    assert "Score: 100" in out
    assert "Score: 5" in out
    assert "[Enlace]" in out
    assert "reddit.com" in out or "example.com" in out


def test_error_shape() -> None:
    out = format_reddit_mcp_json_to_nl('{"success": false, "error": "Not Found"}')
    assert out is not None
    assert "Not Found" in out


def test_if_applicable_passthrough() -> None:
    plain = "Solo texto"
    assert format_reddit_mcp_reply_if_applicable(plain) == plain


def test_single_post_includes_full_selftext_body() -> None:
    long_body = "analysis " * 80
    raw = json.dumps(
        {
            "id": "abc",
            "title": "Isaac Lab?",
            "subreddit": "reinforcementlearning",
            "score": 7,
            "permalink": "/r/reinforcementlearning/comments/abc/x/",
            "is_self": True,
            "selftext": long_body,
        }
    )
    out = format_reddit_mcp_json_to_nl(raw)
    assert out is not None
    assert "**Cuerpo del post:**" in out
    assert long_body.strip()[:200] in out


def test_build_reddit_llm_context_block_wraps_post() -> None:
    raw = json.dumps(
        {
            "id": "1",
            "title": "T",
            "subreddit": "test",
            "score": 1,
            "permalink": "/r/test/comments/1/x/",
            "is_self": False,
        }
    )
    block = build_reddit_llm_context_block(raw)
    assert "[REDDIT_POST_CONTEXT]" in block
    assert "T" in block
    assert "contexto factual" in block


def test_formats_single_reddit_get_post_json() -> None:
    raw = json.dumps(
        {
            "id": "1tmsc97",
            "title": "Suspected Ebola cases in eastern DR Congo pass 900",
            "score": 1395,
            "upvote_ratio": 0.98,
            "num_comments": 69,
            "permalink": "https://reddit.com/r/worldnews/comments/1tmsc97/suspected_ebola/",
            "is_self": False,
        }
    )
    out = format_reddit_mcp_json_to_nl(raw)
    assert out is not None
    assert "## r/worldnews · 1tmsc97" in out
    assert "Suspected Ebola" in out
    assert "Score: 1395" in out
    assert "98% up" in out
    assert "Comentarios: 69" in out
    assert "[Enlace]" in out


def test_caps_posts_and_selftext_length(monkeypatch) -> None:
    monkeypatch.setenv("REDDIT_SELFTEXT_CONTEXT_MAX_CHARS", "200")
    long_body = "x" * 500
    posts = [
        {
            "id": str(i),
            "title": f"Post {i}",
            "score": i,
            "permalink": f"/r/test/comments/{i}/x/",
            "is_self": True,
            "selftext": long_body if i == 0 else "",
        }
        for i in range(15)
    ]
    raw = json.dumps({"subreddit": "test", "posts": posts})
    out = format_reddit_mcp_json_to_nl(raw)
    assert out is not None
    assert f"Top {REDDIT_MCP_LLM_MAX_POSTS} posts" in out
    assert "*Extracto:*" in out
    excerpt_line = [ln for ln in out.splitlines() if ln.strip().startswith("*Extracto:*")][0]
    excerpt = excerpt_line.split("*Extracto:*", 1)[1].strip()
    assert len(excerpt) <= 201
    assert excerpt.endswith("…")


def test_atom_facade_reexports() -> None:
    from duckclaw.forge.atoms.reddit_listing_to_nl import format_reddit_mcp_reply_if_applicable as fac

    assert fac("plain") == "plain"


def test_sanitize_reddit_tool_messages_for_llm() -> None:
    raw_json = json.dumps(
        {
            "subreddit": "worldnews",
            "posts": [
                {
                    "title": "Hello",
                    "score": 1,
                    "permalink": "/r/worldnews/comments/x/hello/",
                    "is_self": False,
                }
            ],
        }
    )
    tm = ToolMessage(content=raw_json, tool_call_id="tc1", name="reddit_get_subreddit_posts")
    human = HumanMessage(content="hi")
    out = sanitize_reddit_tool_messages_for_llm([human, tm])
    assert len(out) == 2
    assert out[0] is human
    assert isinstance(out[1], ToolMessage)
    assert out[1].name == "reddit_get_subreddit_posts"
    body = out[1].content or ""
    assert "## r/worldnews" in body
    assert "Hello" in body
    assert '"posts"' not in body


def test_lc_messages_to_chatml_sanitizes_reddit_tool() -> None:
    from duckclaw.graphs.conversation_traces import _lc_messages_to_chatml

    raw_json = json.dumps(
        {
            "subreddit": "worldnews",
            "posts": [
                {
                    "title": "Trace title",
                    "score": 2,
                    "permalink": "/r/worldnews/comments/y/t/",
                    "is_self": False,
                }
            ],
        }
    )
    tm = ToolMessage(content=raw_json, tool_call_id="id2", name="reddit_get_subreddit_posts")
    chatml = _lc_messages_to_chatml([tm])
    assert len(chatml) == 1
    row = chatml[0]
    assert row["role"] == "tool"
    assert row["name"].startswith("reddit_")
    assert "## r/worldnews" in row["content"]
    assert "Trace title" in row["content"]
