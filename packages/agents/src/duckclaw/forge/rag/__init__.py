"""DuckDB Native RAG — Vector Similarity Search para catálogos.

Spec: docs/architecture/tri_cameral_memory.md
"""

from duckclaw.forge.rag.embeddings import embed_text, get_embedding_model
from duckclaw.forge.rag.catalog import ensure_catalog_schema, search_catalog_semantic
from duckclaw.forge.rag.context_provider import KnowledgeContext, build_knowledge_context, knowledge_inventory_for_project
from duckclaw.forge.rag.context_blocks import (
    CONTEXT_BLOCK_TAGS,
    CONTEXT_FALLBACK_TASK,
    RAG_FALLBACK_TASK,
    extract_tagged_block,
    preserve_context_blocks_for_worker,
    strip_tagged_blocks,
)
from duckclaw.forge.rag.knowledge_core import build_document_payload, build_uploaded_document_payload, search_knowledge
from duckclaw.forge.rag.prompt_policy import rag_turn_system_prompt
from duckclaw.forge.rag.tool_policy import (
    has_rag_context,
    should_prioritize_rag_over_storage_tools,
    without_tools_named,
    without_storage_tools,
)

__all__ = [
    "embed_text",
    "get_embedding_model",
    "ensure_catalog_schema",
    "search_catalog_semantic",
    "KnowledgeContext",
    "build_knowledge_context",
    "knowledge_inventory_for_project",
    "CONTEXT_BLOCK_TAGS",
    "CONTEXT_FALLBACK_TASK",
    "RAG_FALLBACK_TASK",
    "extract_tagged_block",
    "preserve_context_blocks_for_worker",
    "strip_tagged_blocks",
    "build_document_payload",
    "build_uploaded_document_payload",
    "search_knowledge",
    "rag_turn_system_prompt",
    "has_rag_context",
    "should_prioritize_rag_over_storage_tools",
    "without_tools_named",
    "without_storage_tools",
]
