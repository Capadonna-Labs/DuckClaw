"""Entrega de respuestas proactivas /crons según canal configurado."""

from __future__ import annotations

from typing import Any

from duckclaw.homeostasis.goals_alignment import normalize_notify_channel


def resolve_notify_channel(payload: Any, *, chat_state_channel: str = "") -> str:
    """Canal efectivo: payload.notify_channel > chat_state > default."""
    raw = ""
    if isinstance(payload, dict):
        raw = str(payload.get("notify_channel") or "").strip()
    else:
        raw = str(getattr(payload, "notify_channel", None) or "").strip()
    if not raw:
        raw = (chat_state_channel or "").strip()
    return normalize_notify_channel(raw)


def should_deliver_telegram(notify_channel: str, session_id: str) -> bool:
    ch = normalize_notify_channel(notify_channel)
    if ch not in ("telegram", "both"):
        return False
    sid = (session_id or "").strip()
    if not sid:
        return False
    if sid.startswith(("admin-conv-", "admin-playground", "admin-section-", "admin-ui")):
        return False
    return sid.replace("-", "").isdigit() or sid.lstrip("-").isdigit()


def should_persist_admin_history(notify_channel: str, session_id: str) -> bool:
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    ch = normalize_notify_channel(notify_channel)
    if ch not in ("admin", "both"):
        return False
    return is_admin_ui_chat_session(session_id)
