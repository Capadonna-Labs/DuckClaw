"""Pure helpers for preserving tagged RAG context blocks in worker tasks."""

from __future__ import annotations

import re
from collections.abc import Callable

CONTEXT_BLOCK_TAGS = ("PROJECT_CONTEXT", "RAG_SOURCE_INVENTORY", "RAG_CONTEXT")
RAG_FALLBACK_TASK = "Responde al usuario usando el contexto RAG disponible."
CONTEXT_FALLBACK_TASK = "Responde al usuario usando el contexto disponible."


def extract_tagged_block(text: str, tag: str) -> str:
    if not text or not tag:
        return ""
    pattern = re.compile(rf"\[{re.escape(tag)}\].*?\[/{re.escape(tag)}\]", re.DOTALL)
    match = pattern.search(text)
    return match.group(0).strip() if match else ""


def strip_tagged_blocks(text: str, tags: tuple[str, ...]) -> str:
    out = text or ""
    for tag in tags:
        pattern = re.compile(rf"\[{re.escape(tag)}\].*?\[/{re.escape(tag)}\]", re.DOTALL)
        out = pattern.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def preserve_context_blocks_for_worker(
    incoming: str,
    planned_task: str,
    *,
    explicit_storage_request: Callable[[str], bool] | None = None,
) -> str:
    """Preserve grounding blocks that the planner may otherwise summarize away."""
    task = (planned_task or "").strip()
    if not incoming:
        return task
    blocks = [
        extract_tagged_block(incoming, "PROJECT_CONTEXT"),
        extract_tagged_block(incoming, "RAG_SOURCE_INVENTORY"),
        extract_tagged_block(incoming, "RAG_CONTEXT"),
    ]
    blocks = [block for block in blocks if block and block not in task]
    if not blocks:
        return task
    has_rag_blocks = any(block.startswith("[RAG_") for block in blocks)
    if has_rag_blocks:
        user_question = strip_tagged_blocks(incoming, CONTEXT_BLOCK_TAGS)
        is_storage_request = bool(explicit_storage_request and explicit_storage_request(user_question or incoming))
        if not is_storage_request:
            task = user_question or RAG_FALLBACK_TASK
    return "\n\n".join(
        [
            *blocks,
            "[WORKER_TASK]",
            task or CONTEXT_FALLBACK_TASK,
            "[/WORKER_TASK]",
        ]
    )


__all__ = [
    "CONTEXT_BLOCK_TAGS",
    "CONTEXT_FALLBACK_TASK",
    "RAG_FALLBACK_TASK",
    "extract_tagged_block",
    "preserve_context_blocks_for_worker",
    "strip_tagged_blocks",
]
