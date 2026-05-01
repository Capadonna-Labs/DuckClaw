"""Protocols para futuros adaptadores in-process (Slack, Gmail, …)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from duckclaw.channels.types import NormalizedTurn


class InboundAdapter(Protocol):
    """Normaliza payload crudo del proveedor a NormalizedTurn."""

    def normalize_inbound(self, raw: dict[str, Any]) -> NormalizedTurn: ...


class OutboundAdapter(Protocol):
    """Entrega texto al usuario en el canal."""

    def deliver_plain_text(self, *, chat_id: str, user_id: str, text: str, **kwargs: Any) -> bool: ...
