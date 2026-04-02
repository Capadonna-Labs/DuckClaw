"""Allowlist de nombres vs mcp-reddit npm (prefijo reddit_ en versiones recientes)."""

from types import SimpleNamespace

from duckclaw.forge.skills import reddit_bridge as rb
from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model


def test_read_only_allowlist_includes_prefixed_mcp_reddit_names() -> None:
    assert "reddit_get_post" in rb._READ_ONLY_TOOL_NAMES
    assert "reddit_search_reddit" in rb._READ_ONLY_TOOL_NAMES
    assert "get_post" in rb._READ_ONLY_TOOL_NAMES


def test_mutating_allowlist_includes_prefixed_names() -> None:
    assert "reddit_submit_post" in rb._MUTATING_TOOL_NAMES
    assert "reddit_vote" in rb._MUTATING_TOOL_NAMES


def test_mcp_tool_to_structured_exposes_args_schema_for_get_post() -> None:
    tool_spec = SimpleNamespace(
        description="test",
        inputSchema={
            "type": "object",
            "properties": {
                "subreddit": {"type": "string", "description": "Sub name"},
                "post_id": {"type": "string", "description": "Post id"},
            },
            "required": ["subreddit", "post_id"],
        },
    )
    st = rb._mcp_tool_to_structured(object(), tool_spec, "reddit_get_post")
    assert st is not None
    assert st.args_schema is not None
    fields = st.args_schema.model_fields
    assert "subreddit" in fields
    assert "post_id" in fields


def test_mcp_input_schema_optional_fields_not_required() -> None:
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "q"},
            "limit": {"type": "integer", "description": "n"},
        },
        "required": ["query"],
    }
    Model = mcp_input_schema_to_args_model(schema, "reddit_search_reddit")
    m = Model(query="x")
    assert m.query == "x"
    assert m.limit is None
