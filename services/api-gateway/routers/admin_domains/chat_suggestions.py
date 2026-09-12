"""Sugerencias breves de continuación para el input del chat (post-turno, no bloquea el SSE)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import require_admin_key

router = APIRouter(tags=["admin-chat-suggestions"])


class ChatSuggestionsBody(BaseModel):
    chat_id: str = Field(..., max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    last_user_message: str = Field(default="", max_length=8000)
    last_assistant_message: str = Field(default="", max_length=16000)
    vault_db_path: str = Field(default="", max_length=1024)


class ChatSuggestionsAutoBody(BaseModel):
    chat_id: str = Field(..., max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    enabled: bool = False
    vault_db_path: str = Field(default="", max_length=1024)


def _resolve_state_db_path(vault_db_path: str = "") -> str:
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path

    vault = resolve_env_duckdb_path((vault_db_path or "").strip())
    if vault and os.path.isfile(vault):
        return vault
    gw = resolve_env_duckdb_path((get_gateway_db_path() or "").strip())
    return gw if gw and os.path.isfile(gw) else ""


def _read_suggestions_auto(chat_id: str, vault_db_path: str = "") -> bool | None:
    from duckclaw import DuckClaw
    from duckclaw.commands.suggestions_auto import suggestions_auto_enabled

    path = _resolve_state_db_path(vault_db_path)
    if not path:
        return None
    db = DuckClaw(path, read_only=True)
    try:
        return suggestions_auto_enabled(db, chat_id)
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.post("/chat/suggestions", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions(body: ChatSuggestionsBody) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.commands.chat_suggestions import generate_followup_suggestions
    from duckclaw.gateway_db import get_gateway_db_path

    auto = _read_suggestions_auto(body.chat_id, body.vault_db_path)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "suggestions": [],
            "recommended_index": 0,
            "suggestions_auto_enabled": auto,
        }

    def _load_suggestions():
        db = DuckClaw(gw, read_only=True)
        try:
            return generate_followup_suggestions(
                db,
                body.chat_id,
                tenant_id=body.tenant_id,
                last_user_text=body.last_user_message,
                last_assistant_text=body.last_assistant_message,
            )
        finally:
            db.close()

    payload = await asyncio.to_thread(_load_suggestions)
    if isinstance(payload, dict):
        suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
        try:
            recommended_index = int(payload.get("recommended_index") or 0)
        except (TypeError, ValueError):
            recommended_index = 0
    else:
        # Legacy list return (tests / older builds).
        suggestions = list(payload) if isinstance(payload, list) else []
        recommended_index = 0
    if recommended_index < 0 or recommended_index >= len(suggestions):
        recommended_index = 0
    return {
        "suggestions": suggestions,
        "recommended_index": recommended_index,
        "suggestions_auto_enabled": auto,
    }


@router.post("/chat/suggestions/auto", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions_auto(body: ChatSuggestionsAutoBody) -> dict[str, Any]:
    """UI toggle: persist Auto preference for this chat (clears agent suppress when enabling)."""
    from duckclaw import DuckClaw
    from duckclaw.commands.suggestions_auto import set_suggestions_auto_enabled

    path = _resolve_state_db_path(body.vault_db_path)
    if not path:
        return {"ok": False, "error": "vault_unavailable", "suggestions_auto_enabled": None}
    # read_only → typed DB-Writer enqueue (same as loop tools).
    db = DuckClaw(path, read_only=True)
    try:
        ok, err = set_suggestions_auto_enabled(
            db,
            body.chat_id,
            bool(body.enabled),
            tenant_id=body.tenant_id,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
    if not ok:
        return {
            "ok": False,
            "error": err or "persist_failed",
            "suggestions_auto_enabled": None,
        }
    return {"ok": True, "suggestions_auto_enabled": bool(body.enabled)}
