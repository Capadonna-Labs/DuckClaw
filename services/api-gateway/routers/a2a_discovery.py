"""Public A2A Agent Card discovery (no auth)."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from core.admin_identity import open_gateway_db
from duckclaw.admin_worker_catalog import get_worker_by_tenant_worker_id
from duckclaw.agent_card_builder import build_a2a_agent_card_from_db, worker_is_a2a_public

router = APIRouter(tags=["a2a-discovery"])


def _sanitize_worker_id(worker_id: str) -> str:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        raise HTTPException(status_code=400, detail="worker_id inválido")
    return wid


@router.get("/.well-known/agents/{worker_id}/agent-card.json")
async def public_agent_card(worker_id: str) -> JSONResponse:
    wid = _sanitize_worker_id(worker_id)
    tenant_id = "default"
    with open_gateway_db(read_only=True) as db:
        cat = get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=wid)
        if not worker_is_a2a_public(cat, worker_id=wid):
            raise HTTPException(status_code=404, detail="Agent card not discoverable")
        try:
            card = build_a2a_agent_card_from_db(db, wid, tenant_id=tenant_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=card, headers={"Cache-Control": "public, max-age=300"})
