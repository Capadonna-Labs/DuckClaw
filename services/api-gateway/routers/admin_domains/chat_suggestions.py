"""Sugerencias breves de continuación para el input del chat (post-turno, no bloquea el SSE)."""

from __future__ import annotations

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


@router.post("/chat/suggestions", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions(body: ChatSuggestionsBody) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.commands.chat_suggestions import generate_followup_suggestions
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {"suggestions": []}
    db = DuckClaw(gw, read_only=True)
    try:
        suggestions = generate_followup_suggestions(
            db,
            body.chat_id,
            tenant_id=body.tenant_id,
            last_user_text=body.last_user_message,
            last_assistant_text=body.last_assistant_message,
        )
    finally:
        db.close()
    return {"suggestions": suggestions}
