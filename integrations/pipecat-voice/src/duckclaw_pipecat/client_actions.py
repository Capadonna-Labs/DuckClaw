"""
Typed RTVI client actions for DuckClaw admin live voice.

Typed messages over the WebRTC data channel sync agent state with the UI without HTTP round-trips.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

CLIENT_MSG_APP_STATE = "app_state"
CLIENT_MSG_USER_EVENT = "user_event"

SERVER_MSG_UPDATE_STATE = "update_state"
SERVER_MSG_RENDER_WIDGET = "render_widget"

GraphInvokePhase = Literal["graph_invoke", "idle"]


class UpdateStatePayload(TypedDict, total=False):
    type: str
    phase: GraphInvokePhase
    worker_id: str
    elapsed_ms: int


class AppStatePayload(TypedDict, total=False):
    chat_id: str
    worker_id: str
    tenant_id: str
    vault_path: str
    section: str
    variant: Literal["playground", "bubble"]


def build_update_state(
    *,
    phase: GraphInvokePhase,
    worker_id: str,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    """Agent → app: graph phase for UI heartbeats."""
    return {
        "type": SERVER_MSG_UPDATE_STATE,
        "phase": phase,
        "worker_id": worker_id,
        "elapsed_ms": elapsed_ms,
    }


def parse_app_state(data: Any) -> dict[str, Any]:
    """Normalize client app_state payload."""
    if isinstance(data, dict):
        return dict(data)
    return {}
