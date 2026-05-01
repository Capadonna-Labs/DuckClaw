"""Tipos comunes para adaptadores de canal."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChannelName(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    GMAIL = "gmail"


@dataclass
class NormalizedTurn:
    """Evento de entrada ya normalizado (pre-ChatRequest)."""

    channel: ChannelName
    text: str
    routing_key: str
    chat_id: str
    user_id: str
    username: str = "Usuario"
    chat_type: str = "private"
    external_message_id: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    ok: bool
    detail: str = ""
