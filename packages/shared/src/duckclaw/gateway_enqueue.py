"""Fire-and-forget DB writes from Gateway — no blocking poll on the event loop."""

from __future__ import annotations

from typing import Any


def enqueue_admin_command(command: Any, *, user_id: str = "default") -> str:
    """Enqueue typed write; Gateway must not poll synchronously."""
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path

    return enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id=user_id)
