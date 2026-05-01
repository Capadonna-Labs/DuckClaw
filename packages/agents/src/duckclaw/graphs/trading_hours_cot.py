"""
Ventanas horarias America/Bogota para eventos Quant (SYSTEM_EVENT Telegram).

Specs: specs/features/Core-Satellite HRP Weekly + MOC CFD.md (ventana día + MOC PM2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]


COT_TZ_NAME = "America/Bogota"
# Referencia día 08:30–15:00 COT, inclusive por minuto
_REF_OPEN_MIN = 8 * 60 + 30
_REF_CLOSE_MIN = 15 * 60
# Tramo típico MOC PM2 (lun–vie ejemplo): 14:40–14:55 inclusive
_MOC_SLOT_START_MIN = 14 * 60 + 40
_MOC_SLOT_END_MIN = 14 * 60 + 55


def minutes_since_midnight_local(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def classify_cot_trading_windows(dt_cot: datetime) -> dict[str, Any]:
    """
    dt_cot: momento en zona Bogotá (aware). Si llega naive, interpretar como COT estable.
    """
    if ZoneInfo is not None and dt_cot.tzinfo is None:
        dt_cot = dt_cot.replace(tzinfo=ZoneInfo(COT_TZ_NAME))
    wd = dt_cot.weekday()
    weekday_mon_fri = wd < 5
    msm = minutes_since_midnight_local(dt_cot)
    in_equity_ref = bool(
        weekday_mon_fri and _REF_OPEN_MIN <= msm <= _REF_CLOSE_MIN
    )
    in_moc_typical = bool(
        weekday_mon_fri and _MOC_SLOT_START_MIN <= msm <= _MOC_SLOT_END_MIN
    )
    return {
        "weekday_mon_fri": weekday_mon_fri,
        "in_equity_ref_window": in_equity_ref,
        "in_moc_typical_window": in_moc_typical,
        "hhmm": dt_cot.strftime("%H:%M"),
        "yyyymmdd": dt_cot.strftime("%Y-%m-%d"),
    }


def _suffix_instruction(summary: dict[str, Any]) -> str:
    if summary["in_moc_typical_window"]:
        return (
            "Prioriza no contradecir el pipeline PM2 `moc_pipeline.py` "
            "(señales strategy_name=moc_hrp_cfd). Ingestas/resúmenes OK; ejecución batch vía `/execute_all_moc` según spec."
        )
    if summary["in_equity_ref_window"]:
        return (
            "Ventana mercado referencia activa (08:30–15:00 COT lun–vie): "
            "procesar CFD/OHLCV/portfolio y preparar overnight_gap_squeeze/MOC sin sustituir el cron PM2 ni duplicar MOC contradictorio."
        )
    return (
        "Fuera de ventana mercado referencia (08:30–15:00 COT lun–vie): "
        "no asumas sesión intradía; usa `get_current_time` para hora/fecha cuando haga falta. "
        "MOC sigue en PM2 cuando toque (~14:40/14:50/14:55 COT ejemplo)."
    )


def format_contex_horario_line(dt_cot: datetime) -> str:
    c = classify_cot_trading_windows(dt_cot)
    core = (
        f"tz={COT_TZ_NAME}; local={c['yyyymmdd']} {c['hhmm']}; "
        f"lun_vie={c['weekday_mon_fri']}; mercado_ref_0830_1500={c['in_equity_ref_window']}; "
        f"moc_pm2_tipico_1440_1455={c['in_moc_typical_window']}"
    )
    return "[CONTEXTO_HORARIO] " + core + ". " + _suffix_instruction(c)


def now_bogota() -> datetime:
    """Hora actual en America/Bogota (fallback sin zoneinfo = naive local UTC+offset no garantizado — evitar si falta deps)."""
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(tz=ZoneInfo(COT_TZ_NAME))


def quant_event_horario_line(*, dt_cot: datetime | None = None) -> str:
    dt = dt_cot if dt_cot is not None else now_bogota()
    return format_contex_horario_line(dt)
