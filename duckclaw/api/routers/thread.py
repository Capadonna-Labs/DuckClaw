"""Thread router: estado de sesión, takeover y release (HITL Handoff)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/thread", tags=["thread"])

_manager: Any = None


def _get_session_manager() -> Any:
    global _manager
    if _manager is None:
        try:
            from duckclaw.activity.session_state import SessionStateManager
            _manager = SessionStateManager()
        except Exception:
            _manager = False
    return _manager


@router.get("/{thread_id}/status", summary="Estado de sesión")
async def get_thread_status(thread_id: str):
    """
    Retorna el estado: IDLE, BUSY, HANDOFF_REQUESTED, MANUAL_MODE.
    n8n consulta antes de enrutar mensajes.
    """
    mgr = _get_session_manager()
    if not mgr:
        return {"thread_id": thread_id, "status": "IDLE", "context_summary": ""}
    try:
        status = mgr.get_status(thread_id)
        context = mgr.get_context(thread_id)
        return {"thread_id": thread_id, "status": status, "context_summary": context}
    except Exception:
        return {"thread_id": thread_id, "status": "IDLE", "context_summary": ""}


class TakeoverRequest(BaseModel):
    """Payload para takeover (opcional)."""
    reason: str = Field("", description="Motivo del takeover")


@router.post("/{thread_id}/takeover", summary="Humano asume control")
async def thread_takeover(thread_id: str, payload: TakeoverRequest | None = None):
    """
    Cambia estado a MANUAL_MODE. El agente ignora mensajes de este thread.
    n8n/Dashboard llama tras aceptar handoff.
    """
    mgr = _get_session_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Redis no configurado. REDIS_URL requerido.")
    try:
        mgr.takeover(thread_id)
        return {"thread_id": thread_id, "status": "MANUAL_MODE"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ReleaseRequest(BaseModel):
    """Payload para release. Historial de mensajes del humano para inyectar."""
    human_messages: list[dict] = Field(default_factory=list, description="[{role, content}]")


@router.post("/{thread_id}/release", summary="Humano libera control")
async def thread_release(thread_id: str, payload: ReleaseRequest | None = None):
    """
    Cambia estado a IDLE. El agente retoma el control.
    Opcionalmente inyecta human_messages en el historial (DataMasker aplicado).
    """
    mgr = _get_session_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Redis no configurado.")
    try:
        mgr.release(thread_id)
        # TODO: inyectar human_messages en Checkpointer con DataMasker
        return {"thread_id": thread_id, "status": "IDLE"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
