"""Human-readable integration labels from gateway delivery channel + session id."""

from __future__ import annotations


def _is_admin_ui_chat_session(chat_id: str) -> bool:
    """
    Admin console sessions (Next.js playground / conversations).

    Mirrors ``duckclaw.graphs.chat_heartbeat.is_admin_ui_chat_session`` without
    importing the agents package from shared.
    """
    cid = (chat_id or "").strip()
    if not cid:
        return False
    if cid == "admin-playground":
        return True
    if (
        cid.startswith("admin-section-")
        or cid.startswith("admin-ui")
        or cid.startswith("admin-conv-")
    ):
        return True
    return "admin-conv-" in cid


def resolve_integration_label(
    channel: str | None,
    *,
    chat_id: str = "",
) -> tuple[str, str]:
    """
    Map raw gateway channel + optional chat_id to (integration_channel, integration_label).

    The integration label selects the HITL egress channel (Interfaz vs Telegram)
    without coupling the worker to a specific transport.
    """
    ch = (channel or "telegram").strip().lower()
    cid = (chat_id or "").strip()

    if ch == "http" and _is_admin_ui_chat_session(cid):
        return ch, "Interfaz"
    if ch == "telegram":
        return ch, "Telegram"
    if ch == "discord":
        return ch, "Discord"
    if ch in ("edge", "sensory"):
        return ch, "Edge Device"
    if ch == "http":
        return ch, "HTTP"
    return ch, ch or "unknown"


__all__ = ["resolve_integration_label"]
