"""Ventana de acumulación intradía MOC: referencia RTH COT 08:30–15:00 (lun–vie)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]


def reference_rth_cot_now() -> datetime:
    """Momento efectivo para gating accumulate_moc_intraday_state (tests monkeypatch datetime)."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Bogota"))
        except Exception:
            pass
    return datetime.now()


def inside_reference_equity_rth_cot(dt: datetime | None = None) -> tuple[bool, str, dict[str, Any]]:
    """
    Lun–vie America/Bogota, segundos [08:30:00 , 15:00:00] inclusive en ambos extremos.

    Referencia operativa Nasdaq-style (spec Core-Satellite); no calendario de feriados.
    """
    now = dt if dt is not None else reference_rth_cot_now()
    meta: dict[str, Any] = {
        "local_iso": now.date().isoformat() + "T" + now.strftime("%H:%M:%S"),
        "tz": "America/Bogota",
    }
    if now.weekday() >= 5:
        return False, "WEEKEND", meta

    sec = now.hour * 3600 + now.minute * 60 + int(now.second)
    start_s = 8 * 3600 + 30 * 60
    end_s = 15 * 3600
    if sec < start_s or sec > end_s:
        return False, "OUTSIDE_REFERENCE_RTH", meta
    return True, "", meta
