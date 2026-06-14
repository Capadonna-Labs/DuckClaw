"""RAG-aware tool policy.

This module is intentionally small and pure: it decides whether a turn grounded
with RAG context should hide storage-oriented tools such as ``get_db_path``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

RAG_CONTEXT_TAG = "[RAG_CONTEXT]"
RAG_SOURCE_INVENTORY_TAG = "[RAG_SOURCE_INVENTORY]"
STORAGE_TOOL_NAMES = frozenset(
    {
        "admin_sql",
        "get_db_path",
        "get_schema_info",
        "inspect_schema",
        "read_sql",
    }
)


def has_rag_context(text: str | None) -> bool:
    """Return True when the prompt contains project knowledge blocks."""
    raw = text or ""
    return RAG_CONTEXT_TAG in raw or RAG_SOURCE_INVENTORY_TAG in raw


def should_prioritize_rag_over_storage_tools(
    incoming: str | None,
    intent_text: str | None,
    *,
    explicit_storage_request: Callable[[str], bool],
) -> bool:
    """RAG turns should not drift into DuckDB storage answers.

    Storage tools remain available when the user explicitly asks for database,
    table, schema, or vault details.
    """
    if not has_rag_context(incoming):
        return False
    return not explicit_storage_request(intent_text or incoming or "")


def without_tools_named(tools: Iterable[Any], excluded_names: set[str]) -> list[Any]:
    """Return tools excluding names in ``excluded_names``."""
    excluded = {name.strip() for name in excluded_names if name and name.strip()}
    return [
        tool
        for tool in tools
        if str(getattr(tool, "name", "") or "").strip() not in excluded
    ]


def without_storage_tools(tools: Iterable[Any]) -> list[Any]:
    """Hide DuckDB/storage tools for RAG turns that are not DB questions."""
    return without_tools_named(tools, set(STORAGE_TOOL_NAMES))
