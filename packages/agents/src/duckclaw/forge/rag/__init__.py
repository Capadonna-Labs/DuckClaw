"""DuckDB Native RAG — Vector Similarity Search para catálogos.

Spec: specs/DuckDB_Native_RAG_Vector_Search.md
"""

from duckclaw.forge.rag.embeddings import embed_text, get_embedding_model
from duckclaw.forge.rag.catalog import ensure_catalog_schema, search_catalog_semantic
from duckclaw.forge.rag.context_provider import KnowledgeContext, build_knowledge_context, knowledge_inventory_for_project
from duckclaw.forge.rag.knowledge_core import build_document_payload, build_uploaded_document_payload, search_knowledge

__all__ = [
    "embed_text",
    "get_embedding_model",
    "ensure_catalog_schema",
    "search_catalog_semantic",
    "KnowledgeContext",
    "build_knowledge_context",
    "knowledge_inventory_for_project",
    "build_document_payload",
    "build_uploaded_document_payload",
    "search_knowledge",
]
