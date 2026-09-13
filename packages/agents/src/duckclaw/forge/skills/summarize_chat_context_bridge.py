"""Tool always-on: compacta el historial Redis del chat actual (context fold)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List

from langchain_core.tools import StructuredTool

_log = logging.getLogger(__name__)

_HISTORY_KEY_PREFIX = "duckclaw:gateway:chat_hist"


def _history_redis_key(tenant_id: str, session_id: str) -> str:
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "default").strip() or "default"
    return f"{_HISTORY_KEY_PREFIX}:{tid}:{sid}"


def _resolve_history_session_id(chat_id: str) -> str:
    sid = (chat_id or "").strip()
    if not sid:
        return ""
    try:
        from duckclaw.graphs.chat_heartbeat import admin_report_chat_id, is_admin_ui_chat_session

        if is_admin_ui_chat_session(sid):
            return (admin_report_chat_id(sid) or sid).strip() or sid
    except Exception:
        pass
    return sid


def _gateway_chat_history_enabled() -> bool:
    v = (os.environ.get("DUCKCLAW_GATEWAY_CHAT_HISTORY") or "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()


def _normalize_history_list(raw: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw or []:
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
        out.append({"role": role, "content": content})
    max_msgs = int(os.environ.get("DUCKCLAW_CHAT_HISTORY_MAX_MSGS", "48"))
    if len(out) > max_msgs:
        out = out[-max_msgs:]
    return out


def load_gateway_chat_history_sync(tenant_id: str, session_id: str) -> list[dict[str, str]]:
    """Lee historial gateway (Redis) de forma síncrona para tools del worker."""
    if not _gateway_chat_history_enabled():
        return []
    url = _redis_url()
    if not url or not session_id:
        return []
    try:
        import redis

        client = redis.from_url(url, decode_responses=True)
        try:
            raw = client.get(_history_redis_key(tenant_id, session_id))
        finally:
            try:
                client.close()
            except Exception:
                pass
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return _normalize_history_list(data)
    except Exception as exc:
        _log.warning("summarize_chat_context: redis load failed: %s", exc)
        return []


def save_gateway_chat_history_sync(
    tenant_id: str,
    session_id: str,
    items: list[dict[str, str]],
) -> bool:
    """Escribe historial gateway (Redis). Finalize reescribirá con el turno actual."""
    if not _gateway_chat_history_enabled():
        return False
    url = _redis_url()
    if not url or not session_id:
        return False
    norm = _normalize_history_list(items)
    try:
        import redis

        ttl = int(os.environ.get("DUCKCLAW_CHAT_HISTORY_TTL_SEC", "604800"))
        client = redis.from_url(url, decode_responses=True)
        try:
            client.set(
                _history_redis_key(tenant_id, session_id),
                json.dumps(norm, ensure_ascii=False),
                ex=ttl,
            )
        finally:
            try:
                client.close()
            except Exception:
                pass
        return True
    except Exception as exc:
        _log.warning("summarize_chat_context: redis save failed: %s", exc)
        return False


def summarize_chat_context_impl(
    reason: str = "",
    *,
    db: Any = None,
) -> str:
    """Compacta el hilo actual y deja override para que persist no re-infle Redis."""
    from duckclaw.forge.skills.chat_history_compact_context import set_compacted_chat_history
    from duckclaw.forge.skills.goals_tool_context import (
        get_goals_tool_chat_id,
        get_goals_tool_db_path,
        get_goals_tool_tenant_id,
        get_goals_tool_worker_id,
    )

    chat_id = get_goals_tool_chat_id()
    if not chat_id:
        return json.dumps(
            {
                "status": "error",
                "error": "chat_id_unavailable",
                "hint": "summarize_chat_context solo funciona dentro de un turno de chat.",
            },
            ensure_ascii=False,
        )

    tenant_id = (get_goals_tool_tenant_id() or "default").strip() or "default"
    worker_id = (get_goals_tool_worker_id() or "").strip() or None
    vault_path = (get_goals_tool_db_path() or "").strip()
    session_id = _resolve_history_session_id(chat_id)

    history = load_gateway_chat_history_sync(tenant_id, session_id)
    if len(history) < 2:
        return json.dumps(
            {
                "status": "error",
                "error": "insufficient_history",
                "message_count": len(history),
                "hint": "Se necesitan al menos 2 mensajes user/assistant en Redis.",
            },
            ensure_ascii=False,
        )

    fly_db = db
    if fly_db is None and vault_path:
        try:
            from duckclaw.gateway_db import GatewayDbEphemeralReadonly

            fly_db = GatewayDbEphemeralReadonly(vault_path)
        except Exception:
            fly_db = None

    from duckclaw.commands.context_summarize import run_manual_context_fold

    summary, err, meta = run_manual_context_fold(
        fly_db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        history=history,
        vault_db_path=vault_path or None,
    )
    if err:
        return json.dumps(
            {"status": "error", "error": "fold_failed", "detail": err},
            ensure_ascii=False,
        )

    kept = meta.get("kept_history") if isinstance(meta, dict) else None
    kept_history = _normalize_history_list(kept if isinstance(kept, list) else [])
    set_compacted_chat_history(kept_history)

    vault_saved = False
    vault_summary = (summary or "").strip()
    if vault_summary and vault_path:
        try:
            from duckclaw.commands.context_fold_store import save_context_fold_summary

            vault_saved = bool(
                save_context_fold_summary(
                    vault_path,
                    chat_id,
                    vault_summary,
                    tenant_id=tenant_id,
                )
            )
        except Exception as exc:
            _log.warning("summarize_chat_context: vault save failed: %s", exc)

    redis_saved = save_gateway_chat_history_sync(tenant_id, session_id, kept_history)
    tokens = None
    if isinstance(meta, dict) and isinstance(meta.get("context_estimated_tokens"), (int, float)):
        tokens = int(meta["context_estimated_tokens"])

    out: dict[str, Any] = {
        "status": "ok",
        "messages_before": len(history),
        "messages_kept": len(kept_history),
        "summary_chars": len(vault_summary),
        "vault_saved": vault_saved,
        "redis_saved": redis_saved,
        "summary_preview": vault_summary[:500],
    }
    if tokens is not None:
        out["context_estimated_tokens"] = tokens
    note = (reason or "").strip()
    if note:
        out["reason"] = note[:240]
    out["note"] = (
        "Historial Redis compactado. El turno actual se añadirá al finalizar. "
        "El contexto in-graph de este turno puede seguir grande hasta el próximo mensaje."
    )
    return json.dumps(out, ensure_ascii=False)


def register_summarize_chat_context_skill(tools_list: List[Any], db: Any = None) -> None:
    """Registra ``summarize_chat_context`` (fold manual del hilo vía tool)."""

    def summarize_chat_context(reason: str = "") -> str:
        """
        Compacta el historial del chat actual (mismo efecto que /summarize).

        Usa el context monitor LLM, guarda el resumen en la bóveda y reescribe
        Redis con el hilo corto para que los próximos turnos no re-inflen tokens.
        reason: opcional, se refleja en el JSON de resultado.
        """
        return summarize_chat_context_impl(reason, db=db)

    tools_list.append(
        StructuredTool.from_function(
            summarize_chat_context,
            name="summarize_chat_context",
            description=(
                "Compacta el historial del chat (context fold / summarize) cuando el hilo "
                "está hinchado (muchos tools, cuerpos Gmail, etc.). Guarda resumen en bóveda "
                "y reescribe Redis. Preferible a seguir con contexto >100k tokens. "
                "reason: opcional."
            ),
        )
    )
