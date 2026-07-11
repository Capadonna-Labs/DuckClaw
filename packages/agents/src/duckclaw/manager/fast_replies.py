"""Fast-reply helpers for manager smalltalk shortcuts."""

from __future__ import annotations

from typing import Any

from duckclaw.prompt_policies import PromptPolicyResolver


def _manager_greeting_fast_path_ok(incoming: str) -> bool:
    """Short greeting without fly command: skip manager planning and worker delegation."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_simple_greeting

    return _is_simple_greeting(raw)


def _manager_capabilities_fast_path_ok(incoming: str) -> bool:
    """Capabilities smalltalk: respuesta directa sin subagente."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.commands.fast_replies import _is_capabilities_smalltalk

    return _is_capabilities_smalltalk(raw)


def _manager_knowledge_inventory_fast_path_ok(incoming: str) -> bool:
    """Inventario RAG: respuesta directa sin plan ni worker."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.commands.fast_replies import _is_knowledge_inventory_smalltalk

    return _is_knowledge_inventory_smalltalk(raw)


def _knowledge_inventory_fast_reply_text(
    db: Any,
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str,
    knowledge_scope: str,
    worker_id: str | None,
    username: str | None = None,
) -> str:
    from duckclaw.forge.rag.context_provider import knowledge_inventory_for_project
    from duckclaw.knowledge_scope import SCOPE_LABELS_ES, normalize_knowledge_scope

    scope = normalize_knowledge_scope(knowledge_scope, project_id=project_id)
    scope_label = SCOPE_LABELS_ES.get(scope, scope)
    inventory = knowledge_inventory_for_project(
        db,
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        knowledge_scope=scope,
    )
    total_docs = sum(int(row.get("document_count") or 0) for row in inventory)
    total_chunks = sum(int(row.get("chunk_count") or 0) for row in inventory)
    worker = (worker_id or "default").strip() or "default"
    user = (username or "").strip()

    if total_docs == 0 and total_chunks == 0:
        body = (
            f"Actualmente **no hay documentos indexados** en la base de conocimiento (RAG). "
            f"El alcance está configurado como **{scope_label}**, pero está vacío — "
            f"**0 documentos, 0 fragmentos**.\n\n"
            "Puedes subir PDF, Word, Markdown u otros archivos en la sección **Conocimiento** "
            "de la plataforma. Una vez indexados, podré buscar y responder basándome en ese contenido.\n\n"
            "Mientras tanto puedo ayudarte con repositorios GitHub, consultas DuckDB u otras tareas del agente."
        )
    else:
        lines = [
            f"Alcance RAG: **{scope_label}** — **{total_docs}** documento(s), **{total_chunks}** fragmento(s).",
        ]
        for source in inventory[:8]:
            name = str(source.get("display_name") or "fuente").strip()
            docs = int(source.get("document_count") or 0)
            chunks = int(source.get("chunk_count") or 0)
            status = str(source.get("status") or "unknown").strip()
            lines.append(f"- {name} ({status}): {docs} docs, {chunks} chunks")
        body = "\n".join(lines)

    prefix = f"Soy el agente **{worker}**."
    if user and "@" in user:
        prefix = f"Soy el agente **{worker}**. Sesión: **{user}**."
    return f"{prefix}\n\n{body}"


def _greeting_fast_reply_text(
    worker_id: str | None,
    *,
    tenant_id: str | None = None,
    username: str | None = None,
) -> str:
    worker = (worker_id or "default").strip() or "default"
    _ = tenant_id
    user = (username or "").strip()
    if user and "@" in user:
        return f"Hola. Soy el agente **{worker}**. Tú eres **{user}**. ¿En qué puedo ayudarte?"
    return f"Hola. Soy DuckClaw, agente **{worker}**. ¿En qué puedo ayudarte?"


def _capabilities_fast_reply_text(
    worker_id: str | None,
    *,
    tenant_id: str | None = None,
    coordinator_id: str | None = None,
    delegation_pool: list[str] | None = None,
    prompt_policies: PromptPolicyResolver | None = None,
    username: str | None = None,
) -> str:
    if prompt_policies is None:
        raise RuntimeError(
            "capabilities fast reply requires an injected PromptPolicyResolver "
            "with a migrated DuckDB connection"
        )
    coord = (coordinator_id or "").strip()
    pool = [worker for worker in (delegation_pool or []) if (worker or "").strip()]
    worker = (coord or worker_id or "").strip()
    tenant = (tenant_id or "default").strip() or "default"
    if worker:
        body = prompt_policies.format(
            "capability",
            "generic_worker",
            worker_id=worker,
            tenant_id=tenant,
        )
    else:
        body = prompt_policies.load("capability", "default_fallback")
    if pool:
        lines = "\n".join(f"- {agent}" for agent in pool)
        body = f"{body}\n\nOtros agentes en este workspace:\n{lines}"
    user = (username or "").strip()
    if user and "@" in user:
        return f"{body}\n\n**Usuario de esta sesión:** {user}"
    return body


__all__ = [
    "_capabilities_fast_reply_text",
    "_greeting_fast_reply_text",
    "_knowledge_inventory_fast_reply_text",
    "_manager_capabilities_fast_path_ok",
    "_manager_greeting_fast_path_ok",
    "_manager_knowledge_inventory_fast_path_ok",
]
