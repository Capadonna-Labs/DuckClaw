from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
import json

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

CLOCK_CONTEXT_PREFIX = "Reloj del turno (America/Bogota):"


@tool
def get_current_time() -> str:
    """
    Retorna la fecha y hora actual en Colombia (COT).
    Úsala para calcular vencimientos, rangos de fechas o responder preguntas temporales.
    """
    tz = ZoneInfo("America/Bogota")
    now = datetime.now(tz)
    return json.dumps(
        {
            "iso_8601": now.isoformat(),
            "day_of_week": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        }
    )


def clock_context_message() -> SystemMessage:
    """Hora del turno como contexto. No es un tool_call del modelo."""
    return SystemMessage(content=f"{CLOCK_CONTEXT_PREFIX}\n{get_current_time.invoke({})}")


def turn_has_clock_context(messages: list[Any]) -> bool:
    start = 0
    for index, message in enumerate(messages):
        if getattr(message, "type", None) == "human":
            start = index + 1
    return any(_is_clock_context(message) for message in messages[start:])


def _is_clock_context(message: Any) -> bool:
    if getattr(message, "type", None) != "system":
        return False
    return str(getattr(message, "content", "") or "").startswith(CLOCK_CONTEXT_PREFIX)

