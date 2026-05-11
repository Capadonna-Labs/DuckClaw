"""Calendario de acumulación intradía MOC (COT) vs ventana RTH de referencia.

`accumulate_moc_intraday_state` permite **cualquier día y hora** en zona America/Bogota
(incluye fin de semana) para iterar hints hasta MOC. Opt-in ``DUCKCLAW_MOC_ACCUM_BLOCK_WEEKEND=1``
vuelve a bloquear sábado/domingo. La ventana **08:30–15:00** sigue en ``inside_reference_equity_rth_cot``
para ingestas OHLCV y auto-exec.
"""

from __future__ import annotations

import os
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


def _moc_accum_block_weekend_opt_in() -> bool:
    """Restringir acumulación a lun–vie (comportamiento antiguo). Default: fin de semana permitido."""
    v = (os.environ.get("DUCKCLAW_MOC_ACCUM_BLOCK_WEEKEND") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


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


def inside_reference_accumulation_trading_week_cot(dt: datetime | None = None) -> tuple[bool, str, dict[str, Any]]:
    """
    America/Bogota **cualquier** día y hora (sin ventana 08:30–15:00).

    Fin de semana permitido por defecto; ``DUCKCLAW_MOC_ACCUM_BLOCK_WEEKEND=1`` bloquea sáb/dom.
    """
    now = dt if dt is not None else reference_rth_cot_now()
    meta: dict[str, Any] = {
        "local_iso": now.date().isoformat() + "T" + now.strftime("%H:%M:%S"),
        "tz": "America/Bogota",
        "accum_policy": "anytime_cot_including_weekend",
    }
    if _moc_accum_block_weekend_opt_in() and now.weekday() >= 5:
        return False, "WEEKEND", meta
    return True, "", meta
