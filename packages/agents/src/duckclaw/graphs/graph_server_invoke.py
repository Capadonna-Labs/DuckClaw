"""Invocación async del grafo manager (HTTP, gateway y MCP)."""

from __future__ import annotations

import asyncio
import os
from functools import partial
from typing import Any

from duckclaw.graphs.graph_server_ephemeral import (
    invoke_ephemeral_gateway_graph as _invoke_ephemeral_gateway_graph,
)
from duckclaw.graphs.graph_server_llm_config import _ensure_llm_config
from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.utils.logger import extract_usage_from_messages
from duckclaw.channels.integration_labels import resolve_integration_label


def _model_id_from_messages(messages: list[Any] | None) -> str | None:
    """Extrae model id del último AIMessage (OpenRouter/OpenAI response_metadata)."""
    try:
        from langchain_core.messages import AIMessage
    except Exception:
        return None
    for message in reversed(list(messages or [])):
        if not isinstance(message, AIMessage):
            continue
        response_meta = getattr(message, "response_metadata", None) or {}
        if isinstance(response_meta, dict):
            for key in ("model", "model_name"):
                raw = response_meta.get(key)
                if raw:
                    return str(raw).strip()
        for attr in ("model_name", "model"):
            raw = getattr(message, attr, None)
            if raw:
                return str(raw).strip()
    return None


def _parallel_chat_invocations_enabled() -> bool:
    """Alineado con services/api-gateway/main.py (incl. alias CHAT_PARALLEL_INVOCATIONS)."""
    for key in ("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS", "CHAT_PARALLEL_INVOCATIONS"):
        if (os.environ.get(key) or "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


async def _ainvoke(
    graph: Any,
    message: str,
    history: list,
    chat_id: str,
    *,
    tenant_id: str = "default",
    user_id: str | None = None,
    user_incoming: str | None = None,
    username: str | None = None,
    vault_db_path: str | None = None,
    shared_db_path: str | None = None,
    is_system_prompt: bool | None = False,
    outbound_telegram_bot_token: str | None = None,
    entry_worker_id: str | None = None,
    integration_channel: str | None = None,
    project_id: str | None = None,
    knowledge_scope: str | None = None,
) -> dict:
    """
    Invoca el grafo y retorna {"reply": str, "messages": list | None}.
    messages (cuando existe) es la secuencia completa del turno para trazas SFT (tool_calls, tool, assistant).
    """
    # `input` primero: LangSmith suele usar esta clave para la columna **Input** en la tabla Runs
    # (convención LangChain). `incoming` sigue siendo la fuente de verdad en el grafo.
    _tok = (outbound_telegram_bot_token or "").strip() or None
    _state_user_incoming = (user_incoming or message or "").strip()
    state: dict[str, Any] = {
        "input": message,
        "incoming": message,
        "user_incoming": _state_user_incoming,
        "history": history or [],
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "user_id": (user_id or "").strip() or str(chat_id),
        "username": (username or "").strip(),
        "vault_db_path": (vault_db_path or "").strip() or "",
        "shared_db_path": (shared_db_path or "").strip() or "",
    }
    if _tok:
        state["outbound_telegram_bot_token"] = _tok
    if is_system_prompt:
        state["is_system_prompt"] = True
    _ew = (entry_worker_id or "").strip()
    if _ew:
        state["entry_worker_id"] = _ew
    _pid = (project_id or "").strip()
    if _pid:
        state["project_id"] = _pid
    _scope = (knowledge_scope or "").strip()
    if _scope:
        state["knowledge_scope"] = _scope
    _ich, _ilbl = resolve_integration_label(integration_channel, chat_id=chat_id)
    state["integration_channel"] = _ich
    state["integration_label"] = _ilbl
    _vault = (vault_db_path or "").strip()
    if _vault:
        try:
            from duckclaw.commands.context_fold_store import load_context_fold_summary

            _fold = load_context_fold_summary(_vault, chat_id)
            if _fold:
                state["analytical_summary"] = _fold
        except Exception:
            pass
    loop = asyncio.get_event_loop()

    trace_cfg = get_tracing_config(tenant_id, "manager", chat_id)
    # ainvoke sigue ejecutando nodos síncronos (p. ej. worker_graph.invoke) en el event loop
    # y bloquea otras peticiones HTTP. Con paralelismo por chat, mover invoke a un hilo.
    if _parallel_chat_invocations_enabled():
        result = await asyncio.to_thread(graph.invoke, state, trace_cfg)
    elif hasattr(graph, "ainvoke"):
        result = await graph.ainvoke(state, trace_cfg)
    else:
        result = await loop.run_in_executor(None, partial(graph.invoke, state, trace_cfg))

    reply = str(result.get("reply") or result.get("output") or "Sin respuesta.")
    messages = result.get("messages")
    usage = extract_usage_from_messages(messages)
    out: dict[str, Any] = {"reply": reply, "messages": messages}
    if usage:
        out["usage_tokens"] = usage
    model_id = _model_id_from_messages(messages)
    if model_id:
        out["model"] = model_id
    # Manager -> subagente: propagar para logs/auditoria en el API Gateway.
    for _k in (
        "assigned_worker_id",
        "plan_title",
        "_audit_done",
        "sandbox_photo_base64",
        "visual_artifact_id",
        "outbound_image_paths",
        "analytical_summary",
    ):
        if _k in result:
            out[_k] = result[_k]
    _vault_save = (vault_db_path or "").strip()
    if _vault_save:
        _summary = (result.get("analytical_summary") or "").strip()
        if _summary:
            try:
                from duckclaw.commands.context_fold_store import save_context_fold_summary

                save_context_fold_summary(
                    _vault_save,
                    chat_id,
                    _summary,
                    tenant_id=tenant_id,
                )
            except Exception:
                pass
    return out


async def ainvoke_manager_ephemeral(
    message: str,
    history: list,
    chat_id: str,
    *,
    tenant_id: str = "default",
    user_id: str | None = None,
    user_incoming: str | None = None,
    username: str | None = None,
    vault_db_path: str | None = None,
    shared_db_path: str | None = None,
    is_system_prompt: bool | None = False,
    outbound_telegram_bot_token: str | None = None,
    entry_worker_id: str | None = None,
    integration_channel: str | None = None,
    project_id: str | None = None,
    knowledge_scope: str | None = None,
) -> dict:
    """
    Compila el manager con un DuckClaw RO efímero al gateway, invoca y cierra.
    Uso recomendado desde services/api-gateway en lugar de retener un grafo global.
    """
    from duckclaw.manager.graph import trim_worker_graph_cache

    _ensure_llm_config()
    from functools import partial

    graph, db = await asyncio.to_thread(
        partial(
            _invoke_ephemeral_gateway_graph,
            chat_id,
            vault_db_path,
            tenant_id=tenant_id,
            actor_email=(user_id or username or ""),
        )
    )
    try:
        return await _ainvoke(
            graph,
            message,
            history,
            chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_incoming=user_incoming,
            username=username,
            vault_db_path=vault_db_path,
            shared_db_path=shared_db_path,
            is_system_prompt=is_system_prompt,
            outbound_telegram_bot_token=outbound_telegram_bot_token,
            entry_worker_id=entry_worker_id,
            integration_channel=integration_channel,
            project_id=project_id,
            knowledge_scope=knowledge_scope,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
        trim_worker_graph_cache()
