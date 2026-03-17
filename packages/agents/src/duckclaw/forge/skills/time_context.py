from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import json

from langchain_core.tools import tool


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

