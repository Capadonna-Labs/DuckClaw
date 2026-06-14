"""Prompt policy lookup for RAG-grounded turns."""

from __future__ import annotations

from duckclaw.prompt_policies import PromptPolicyResolver


def rag_turn_system_prompt(resolver: PromptPolicyResolver, worker_id: str) -> str:
    """Return the DB-backed system prompt for a RAG turn."""
    label = (worker_id or "agente").strip() or "agente"
    return resolver.format("system_prompt", "rag_turn", worker_id=label)
