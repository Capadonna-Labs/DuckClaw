"""Comando /summarize — compactación manual del hilo (context monitor)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from duckclaw.commands.chat_state import get_chat_state
from duckclaw.commands.context_fold_store import load_context_fold_summary
from duckclaw.commands.model_setup import _effective_llm_triplet_for_chat_ui
from duckclaw.commands.workers import _DEFAULT_WORKER
from duckclaw.workers.context_monitor import apply_context_monitor_state, build_summary_llm
from duckclaw.workers.loader import append_domain_closure_block, load_system_prompt
from duckclaw.workers.manifest import load_manifest
from duckclaw.workers.provider_input_budget import (
    context_prune_globally_enabled,
    estimate_tokens_from_messages,
    normalized_context_pruning,
)

_log = logging.getLogger(__name__)


def _catalog_db_for_manifest() -> Any | None:
    """Catálogo de workers vive en hub gateway, no en bóveda por conversación."""
    try:
        from duckclaw.graphs.graph_server import get_db

        return get_db()
    except Exception:
        return None


def _vault_db_path_from_handle(db: Any) -> str:
    raw = str(getattr(db, "_path", "") or "").strip()
    if not raw or raw == ":memory:":
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except OSError:
        return raw


def _history_rows_from_query(db: Any, sql: str) -> list[dict[str, str]]:
    try:
        raw = db.query(sql)
    except Exception:
        return []
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        if role in ("human", "user"):
            role = "user"
        elif role in ("ai", "assistant"):
            role = "assistant"
        else:
            continue
        out.append({"role": role, "content": content})
    return out


def load_vault_conversation_history(db: Any, chat_id: Any) -> list[dict[str, str]]:
    """Historial persistido en bóveda (api_conversation o telegram_conversation)."""
    sid = str(chat_id).replace("'", "''")[:256]
    rows = _history_rows_from_query(
        db,
        f"SELECT role, content FROM api_conversation WHERE session_id = '{sid}' "
        "ORDER BY created_at ASC",
    )
    if rows:
        return rows
    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return []
    return _history_rows_from_query(
        db,
        f"SELECT role, content FROM telegram_conversation WHERE chat_id = {cid} "
        "ORDER BY created_at ASC",
    )


def _merge_history(
    explicit: list[dict[str, Any]] | None,
    db: Any,
    chat_id: Any,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    if explicit:
        for item in explicit:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if role == "human":
                role = "user"
            if role not in ("user", "assistant"):
                continue
            merged.append({"role": role, "content": content})
    if merged:
        return merged
    return load_vault_conversation_history(db, chat_id)


def _history_to_langchain_messages(history: list[dict[str, str]], system_prompt: str) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    messages: list[Any] = [SystemMessage(content=system_prompt)]
    for item in history:
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        else:
            messages.append(AIMessage(content=item["content"]))
    return messages


def _messages_to_kept_history(messages: list[Any]) -> list[dict[str, str]]:
    """Convierte tail post-fold a historial Redis (solo user/assistant)."""
    from langchain_core.messages import AIMessage, HumanMessage

    kept: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            text = str(message.content or "").strip()
            if text:
                kept.append({"role": "user", "content": text})
        elif isinstance(message, AIMessage):
            text = str(message.content or "").strip()
            if text:
                kept.append({"role": "assistant", "content": text})
    return kept


def run_manual_context_fold(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    worker_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
    vault_db_path: str | None = None,
    fold_focus: str = "default",
    alignment_preface: str = "",
) -> tuple[str | None, str | None, dict[str, Any]]:
    """
    Ejecuta fold LLM del hilo.

    Returns:
        (summary_text, error_message, meta) — meta incluye tokens estimados e historial recortado.
    """
    empty_meta: dict[str, Any] = {}
    if not context_prune_globally_enabled():
        return None, (
            "Context monitor desactivado globalmente "
            "(DUCKCLAW_CONTEXT_PRUNE_ENABLED=0)."
        ), empty_meta

    tid = (tenant_id or "default").strip() or "default"
    chat_state_wid = (get_chat_state(db, chat_id, "worker_id") or "").strip()
    wid = (worker_id or chat_state_wid or _DEFAULT_WORKER).strip() or _DEFAULT_WORKER
    catalog_db = _catalog_db_for_manifest()
    try:
        spec = load_manifest(wid, db=catalog_db, tenant_id=tid)
    except Exception as exc:
        return None, str(exc), empty_meta
    pruning = normalized_context_pruning(spec)
    if not pruning.get("enabled"):
        return None, (
            f"Context monitor desactivado para el worker `{wid}` "
            "(context_pruning.enabled: false en manifest)."
        ), empty_meta

    hist = _merge_history(history, db, chat_id)
    if len(hist) < 2:
        return None, "No hay suficiente historial para compactar (mínimo 2 mensajes).", empty_meta

    prompt_base = append_domain_closure_block(load_system_prompt(spec), spec)
    provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
    try:
        from duckclaw.integrations.llm_providers import build_llm

        primary_llm = build_llm(provider, model, base_url)
    except Exception as exc:
        _log.warning("summarize: build_llm failed: %s", exc)
        return None, f"No se pudo inicializar el LLM de resumen: {exc}", empty_meta

    summary_llm = build_summary_llm(
        primary_llm,
        provider=provider or "",
        model=model or "",
        base_url=base_url or "",
    )
    if summary_llm is None:
        return None, "No hay LLM disponible para generar el resumen.", empty_meta

    vault_path = (vault_db_path or _vault_db_path_from_handle(db) or "").strip()
    prior = load_context_fold_summary(vault_path, str(chat_id)) if vault_path else ""
    if not prior:
        prior = (get_chat_state(db, chat_id, "context_fold_summary") or "").strip()

    state = {
        "chat_id": str(chat_id),
        "tenant_id": tid,
        "messages": _history_to_langchain_messages(hist, prompt_base),
        "analytical_summary": prior,
    }
    out = apply_context_monitor_state(
        state,
        pruning_config=pruning,
        prompt_base=prompt_base,
        llm_summary=summary_llm,
        force_prune=True,
        fold_focus=fold_focus,
        alignment_preface=alignment_preface,
    )
    new_summary = (out.get("analytical_summary") or "").strip()
    if not new_summary:
        return None, "No se generó resumen (el fold no produjo texto).", empty_meta

    folded_messages = list(out.get("messages") or [])
    context_estimated_tokens = estimate_tokens_from_messages(folded_messages)
    kept_history = _messages_to_kept_history(folded_messages[1:] if folded_messages else [])
    meta = {
        "summary_for_vault": new_summary,
        "context_estimated_tokens": context_estimated_tokens,
        "kept_history": kept_history,
    }
    return new_summary, None, meta


def execute_summarize_with_meta(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: str = "default",
    history: list[dict[str, Any]] | None = None,
    vault_db_path: str | None = None,
    worker_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Como ``execute_summarize`` pero retorna metadata para gateway/UI."""
    arg = (args or "").strip().lower()
    if arg in ("help", "-h", "--help"):
        return (
            "Uso: `/summarize`\n"
            "Compacta el historial de la conversación con el context monitor (LLM) "
            "y guarda el resumen en la bóveda conectada.\n"
            "Requiere bóveda DuckDB y al menos 2 mensajes en el hilo.",
            {},
        )

    summary, err, meta = run_manual_context_fold(
        db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        history=history,
        vault_db_path=vault_db_path,
    )
    if err:
        return f"⚠️ {err}", {}
    kept = len(summary or "")
    full_body = (summary or "").strip()
    reply = (
        "✅ Hilo compactado manualmente.\n"
        f"Resumen guardado ({kept} caracteres).\n\n"
        f"{full_body}"
    )
    return reply, meta


def execute_summarize(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: str = "default",
    history: list[dict[str, Any]] | None = None,
    vault_db_path: str | None = None,
    worker_id: str | None = None,
) -> str:
    """``/summarize``: compacta el hilo manualmente y persiste el resumen en la bóveda."""
    arg = (args or "").strip().lower()
    if arg in ("help", "-h", "--help"):
        return (
            "Uso: `/summarize`\n"
            "Compacta el historial de la conversación con el context monitor (LLM) "
            "y guarda el resumen en la bóveda conectada.\n"
            "Requiere bóveda DuckDB y al menos 2 mensajes en el hilo."
        )

    summary, err, _meta = run_manual_context_fold(
        db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        history=history,
        vault_db_path=vault_db_path,
    )
    if err:
        return f"⚠️ {err}"
    kept = len(summary or "")
    full_body = (summary or "").strip()
    return (
        "✅ Hilo compactado manualmente.\n"
        f"Resumen guardado ({kept} caracteres).\n\n"
        f"{full_body}"
    )


__all__ = [
    "execute_summarize",
    "execute_summarize_with_meta",
    "load_vault_conversation_history",
    "run_manual_context_fold",
]
