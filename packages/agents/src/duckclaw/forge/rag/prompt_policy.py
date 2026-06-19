"""Prompt policy lookup for RAG-grounded turns."""

from __future__ import annotations

from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.prompt_policies.system_prompt import format_system_prompt_template


def rag_turn_system_prompt(
    resolver: PromptPolicyResolver,
    worker_id: str,
    *,
    tenant_id: str | None = None,
) -> str:
    """Return the DB-backed system prompt for a RAG turn."""
    label = (worker_id or "agente").strip() or "agente"
    tid = (tenant_id or "default").strip() or "default"
    raw = resolver.load("system_prompt", "rag_turn")
    return format_system_prompt_template(raw, worker_id=label, tenant_id=tid)
