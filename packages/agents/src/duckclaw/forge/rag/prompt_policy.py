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


def playground_document_turn_system_prompt() -> str:
    """Instructions for a chat turn containing already-extracted attachments."""
    return """[MODO_ANALISIS_DE_ADJUNTO]
El usuario adjuntó uno o más documentos y su contenido extraído está incluido
en el último mensaje. Analízalo directamente y responde a la petición del
usuario usando ese contenido.

No desvíes la respuesta hacia la base de datos del worker ni sugieras comandos,
herramientas, rutas internas, vaults o nombres de tools. No afirmes que falta
una herramienta si el contenido del adjunto ya permite responder. Si el
documento está incompleto, corrupto o no contiene el dato pedido, dilo de forma
clara y especifica qué falta.
[/MODO_ANALISIS_DE_ADJUNTO]"""
