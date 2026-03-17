from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Payload de chat multi-usuario para el API Gateway.

    - chat_id: identifica el grupo o el DM (se usa como thread_id interno).
    - user_id / username: identifican al remitente dentro del grupo.
    - chat_type: "private", "group", "supergroup", etc.
    """

    message: str = Field(..., description="Mensaje del usuario")
    chat_id: str | None = Field(None, description="ID del chat o grupo (thread_id)")
    user_id: str | None = Field(None, description="ID único del usuario que envió el mensaje")
    username: str | None = Field("Usuario", description="Nombre o alias del usuario")
    chat_type: str | None = Field("private", description="Tipo de chat: private, group, supergroup, etc.")
    history: list[Any] = Field(default_factory=list, description="Historial opcional de mensajes")
    stream: bool | None = Field(False, description="Streaming SSE")
    is_system_prompt: bool | None = Field(
        False,
        description="Marca mensajes internos del sistema (ej. [SYSTEM_EVENT] del Heartbeat).",
    )

