"""RAG-aware tool policy.

This module is intentionally small and pure: it decides whether a turn grounded
with RAG context should hide storage-oriented tools.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

RAG_CONTEXT_TAG = "[RAG_CONTEXT]"
RAG_SOURCE_INVENTORY_TAG = "[RAG_SOURCE_INVENTORY]"
PLAYGROUND_DOCUMENTS_TAG = "[DOCUMENTOS_ADJUNTOS]"
PLAYGROUND_DOCUMENT_BLOCK_TAG = "[Documento adjunto:"
USER_REQUEST_MARKER = "--- Mensaje del usuario ---"
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


def has_playground_documents(text: str | None) -> bool:
    """Return True when the turn carries text extracted from chat attachments."""
    raw = text or ""
    return PLAYGROUND_DOCUMENTS_TAG in raw or PLAYGROUND_DOCUMENT_BLOCK_TAG in raw


def user_request_text(text: str | None) -> str:
    """Return only what the user typed, without attachment or context blocks.

    Attachment text and injected project/RAG blocks surround the user request, so
    matching intent against the whole turn reads spreadsheet rows or a project
    description as if they were a database question.
    """
    raw = text or ""
    if USER_REQUEST_MARKER in raw:
        return raw.rsplit(USER_REQUEST_MARKER, 1)[1].strip()
    return raw.strip()


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


def should_prioritize_documents_over_storage_tools(
    incoming: str | None,
    intent_text: str | None,
    *,
    explicit_storage_request: Callable[[str], bool],
) -> bool:
    """Keep attached-document analysis from drifting into worker DuckDB tools.

    The attachment text is already supplied in the human turn.  Storage tools are
    relevant only when the user explicitly asks a separate database question.
    """
    if not (has_playground_documents(incoming) or has_playground_documents(intent_text)):
        return False
    request = user_request_text(intent_text) or user_request_text(incoming)
    return not explicit_storage_request(request)


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
