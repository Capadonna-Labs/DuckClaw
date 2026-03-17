from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from duckclaw.forge.skills import time_context


def test_get_current_time_returns_valid_json() -> None:
    raw = time_context.get_current_time.invoke({})  # type: ignore[attr-defined]
    data = json.loads(raw)
    assert "iso_8601" in data
    assert "day_of_week" in data
    assert "date" in data
    assert "time" in data


def test_get_current_time_uses_america_bogota() -> None:
    raw = time_context.get_current_time.invoke({})  # type: ignore[attr-defined]
    data = json.loads(raw)
    tz = ZoneInfo("America/Bogota")
    now = datetime.now(tz)
    # Comparamos solo la fecha, para evitar pequeños desajustes de segundos
    assert data["date"] == now.strftime("%Y-%m-%d")

