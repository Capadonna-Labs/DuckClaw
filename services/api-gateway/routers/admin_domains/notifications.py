from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, admin_audit, require_admin_key

router = APIRouter(prefix="/notifications", tags=["admin-notifications"])


class WebPushKeys(BaseModel):
    p256dh: str = Field(..., min_length=16, max_length=512)
    auth: str = Field(..., min_length=8, max_length=256)


class WebPushSubscription(BaseModel):
    endpoint: str = Field(..., min_length=12, max_length=2048)
    expirationTime: int | None = None
    keys: WebPushKeys


class WebPushSubscriptionBody(BaseModel):
    subscription: WebPushSubscription
    device_label: str = "DuckClaw Admin"
    tenant_id: str = "global"


class WebPushTestBody(BaseModel):
    title: str = "DuckClaw"
    body: str = "Notificaciones Web Push activas."
    url: str = "/"
    tag: str = "duckclaw-test"


def _subscription_key(endpoint: str) -> str:
    digest = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:32]
    return f"sub_{digest}"


def _enqueue_subscription(body: WebPushSubscriptionBody, *, actor: str, key: str) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    payload: dict[str, Any] = {
        "subscription": body.subscription.model_dump(mode="json"),
        "device_label": body.device_label[:128],
    }
    command = UpsertRuntimeSettingCommand(
        tenant_id=(body.tenant_id or "global").strip() or "global",
        actor_email=actor,
        domain="web_push",
        key=key,
        value="",
        value_json=payload,
        value_kind="json",
        secret=False,
        updated_by=actor,
    )
    return enqueue_typed_command(command, db_path=str(get_gateway_db_path()), user_id=actor)


@router.get("/web-push/public-key", dependencies=[Depends(require_admin_key)])
async def web_push_public_key() -> dict[str, Any]:
    from duckclaw.web_push import vapid_public_key, web_push_configured

    public_key = vapid_public_key()
    return {"public_key": public_key, "configured": web_push_configured(), "subscribe_enabled": bool(public_key)}


@router.post("/web-push/subscriptions", dependencies=[Depends(require_admin_key)])
async def upsert_web_push_subscription(
    body: WebPushSubscriptionBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    key = _subscription_key(body.subscription.endpoint)
    task_id = await asyncio.to_thread(_enqueue_subscription, body, actor=actor, key=key)
    admin_audit(
        "notifications.web_push.subscribe",
        key,
        body.device_label[:128],
        actor=actor,
        meta={"tenant_id": body.tenant_id},
    )
    return {"ok": True, "queued": True, "key": key, "task_id": task_id}


@router.post("/web-push/test", dependencies=[Depends(require_admin_key)])
async def test_web_push(body: WebPushTestBody) -> dict[str, Any]:
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.web_push import list_web_push_subscriptions, send_web_push_notifications, web_push_configured

    db_path = str(get_gateway_db_path())
    subscriptions = await asyncio.to_thread(list_web_push_subscriptions, db_path)
    result = await asyncio.to_thread(
        send_web_push_notifications,
        subscriptions,
        title=body.title,
        body=body.body,
        url=body.url,
        tag=body.tag,
    )
    if subscriptions and not web_push_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": result.error or "web_push_not_configured", "subscriptions": len(subscriptions)},
        )
    return {
        "ok": result.failed == 0 and not result.error,
        "subscriptions": len(subscriptions),
        "sent": result.sent,
        "failed": result.failed,
        "skipped": result.skipped,
        "error": result.error,
    }