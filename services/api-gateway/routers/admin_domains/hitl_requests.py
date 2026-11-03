"""Approve / reject a pending HITL request through the extension that owns it (the core knows no vertical)."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

_log = logging.getLogger(__name__)
router = APIRouter(tags=["admin-hitl-requests"])


class HitlActBody(BaseModel):
    kind: str = Field(..., min_length=1, max_length=32)
    id: str = Field(..., min_length=8, max_length=64)
    action: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


def _handler():
    """DUCKCLAW_HITL_ENTRYPOINT = ``module:callable`` under the extension lib; None when no extension provides one."""
    from duckclaw.extensions.loader import extension_roots, resolve_callable_entrypoint

    entry = (os.environ.get("DUCKCLAW_HITL_ENTRYPOINT") or "").strip()
    for root in extension_roots() if entry else []:
        fn = resolve_callable_entrypoint(entry, root=root, package_name=None, lib_path=None)
        if fn is not None:
            return fn
    return None


def _notify(body: HitlActBody, result: dict[str, Any]) -> None:
    """Web Push to the admin devices that a decision went through (best effort: a push problem never fails the decision)."""
    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.web_push import list_web_push_subscriptions, send_web_push_notifications

        tag = "hitl-decision"
        subs = list_web_push_subscriptions(str(get_gateway_db_path()), tag)
        if subs:
            verb = "aprobada" if body.action == "approve" else "rechazada"
            send_web_push_notifications(subs, title=f"HITL {body.kind}: {verb}", body=str(result.get("message") or body.id)[:300], url="/", tag=tag)
    except Exception:  # noqa: BLE001
        _log.warning("hitl push failed", exc_info=True)


@router.post("/hitl/requests/act", dependencies=[Depends(require_admin_key)])
async def act_on_hitl_request(body: HitlActBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    fn = _handler()
    if fn is None:
        raise problem(503, "Sin proveedor HITL", "Ninguna extensión declara DUCKCLAW_HITL_ENTRYPOINT")
    result = await asyncio.to_thread(fn, body.kind, body.id.strip(), body.action, body.note, actor)
    if not isinstance(result, dict):
        raise problem(502, "Respuesta HITL inválida", str(result)[:200])
    if result.get("ok"):
        await asyncio.to_thread(_notify, body, result)
    return result
