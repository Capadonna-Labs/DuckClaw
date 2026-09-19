"""Persistent Web Push subscriptions and best-effort delivery."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from duckclaw.duckdb_read_compat import duckclaw_open_for_read_scan

logger = logging.getLogger(__name__)

WEB_PUSH_DOMAIN = "web_push"
WEB_PUSH_SUB_PREFIX = "sub_"


@dataclass(frozen=True)
class WebPushDeliveryResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""


def vapid_public_key() -> str:
    return (os.environ.get("WEB_PUSH_VAPID_PUBLIC_KEY") or "").strip()


def vapid_private_key() -> str:
    return (os.environ.get("WEB_PUSH_VAPID_PRIVATE_KEY") or "").strip()


def vapid_subject() -> str:
    return (os.environ.get("WEB_PUSH_SUBJECT") or "mailto:admin@duckclaw.local").strip()


def web_push_configured() -> bool:
    return bool(vapid_public_key() and vapid_private_key())


def _rows_from_query(raw: Any) -> list[dict[str, Any]]:
    rows = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("[") else (raw or [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _subscription_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("value_json") or row.get("value_text") or ""
    if isinstance(raw, str):
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, dict):
        payload = raw
    else:
        return None
    subscription = payload.get("subscription") if isinstance(payload, dict) else None
    if not isinstance(subscription, dict):
        return None
    endpoint = str(subscription.get("endpoint") or "").strip()
    keys = subscription.get("keys")
    if not endpoint or not isinstance(keys, dict):
        return None
    return subscription


def list_web_push_subscriptions(db_path: str) -> list[dict[str, Any]]:
    """Read active Web Push subscriptions from the hub DB without taking a write lock."""
    try:
        with duckclaw_open_for_read_scan(db_path) as db:
            raw = db.query(
                "SELECT key, value_json, value_text FROM main.admin_runtime_settings "
                "WHERE active = true AND domain = 'web_push' AND key LIKE 'sub_%'"
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("web_push: no subscriptions readable from %s: %s", db_path, exc)
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _rows_from_query(raw):
        subscription = _subscription_from_row(row)
        if not subscription:
            continue
        endpoint = str(subscription.get("endpoint") or "")
        if endpoint in seen:
            continue
        seen.add(endpoint)
        out.append(subscription)
    return out


def send_web_push_notifications(
    subscriptions: list[dict[str, Any]],
    *,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "duckclaw",
) -> WebPushDeliveryResult:
    """Send one notification payload to subscriptions when pywebpush is available."""
    if not subscriptions:
        return WebPushDeliveryResult(skipped=0)
    public_key = vapid_public_key()
    private_key = vapid_private_key()
    if not public_key or not private_key:
        return WebPushDeliveryResult(skipped=len(subscriptions), error="web_push_vapid_not_configured")
    try:
        from pywebpush import WebPushException, webpush  # type: ignore
    except Exception:  # noqa: BLE001
        return WebPushDeliveryResult(skipped=len(subscriptions), error="pywebpush_not_installed")

    payload = json.dumps(
        {"title": title[:120], "body": body[:512], "url": url or "/", "tag": tag[:120]},
        ensure_ascii=False,
    )
    sent = failed = 0
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": vapid_subject()},
            )
            sent += 1
        except WebPushException as exc:
            failed += 1
            logger.warning("web_push: delivery failed status=%s", getattr(exc.response, "status_code", "?"))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("web_push: delivery failed: %s", exc)
    return WebPushDeliveryResult(sent=sent, failed=failed)