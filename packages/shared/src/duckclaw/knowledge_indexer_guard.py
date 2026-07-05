"""Prevent heavy RAG indexing from running inside DuckClaw-Gateway."""

from __future__ import annotations

from duckclaw.process_role import embed_knowledge_sync_in_gateway, is_gateway_process


class KnowledgeIndexingInGatewayError(RuntimeError):
    """Raised when indexing is attempted in the HTTP gateway process."""


def assert_indexer_process_for_mutation(*, operation: str) -> None:
    if is_gateway_process() and not embed_knowledge_sync_in_gateway():
        raise KnowledgeIndexingInGatewayError(
            f"{operation} must run in DuckClaw-Knowledge-Indexer (Gateway is enqueue-only). "
            "Start: pm2 start config/ecosystem.knowledge-indexer.config.cjs"
        )
