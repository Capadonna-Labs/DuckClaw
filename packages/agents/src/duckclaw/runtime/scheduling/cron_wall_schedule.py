"""
Horario de reloj para /crons --timestamp (aparte de --delta). Funciones puras + parseo CLI.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = Any  # type: ignore[misc, assignment]

CRON_WALL_V1 = 1


def default_cron_wall_tz() -> str:
    return (os.getenv("DUCKCLAW_CRONS_WALL_TZ") or "America/Bogota").strip() or "America/Bogota"


_WD_MAP: dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "lun": 0,
    "lunes": 0,
    "tue": 1,
    "tuesday": 1,
    "mar": 1,
    "martes": 1,
    "wed": 2,
    "wednesday": 2,
    "mie": 2,
    "mié": 2,
    "miercoles": 2,
    "miércoles": 2,
    "thu": 3,
    "thursday": 3,
    "jue": 3,
    "jueves": 3,
    "fri": 4,
    "friday": 4,
    "vie": 4,
    "viernes": 4,
    "sat": 5,
    "saturday": 5,
    "sab": 5,
    "sáb": 5,
    "sabado": 5,
    "sábado": 5,
    "sun": 6,
    "sunday": 6,
    "dom": 6,
    "domingo": 6,
}


def _zone(tz_name: str) -> Any:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Bogota")


def parse_hhmm(token: str) -> Optional[tuple[int, int]]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", (token or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def parse_once_datetime(token: str, tz_name: str) -> Optional[tuple[int, int, int, int, int]]:
    s = (token or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T\s](\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    y, mo, d, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
    if mo < 1 or mo > 12 or d < 1 or d > 31 or h > 23 or mi > 59:
        return None
    return y, mo, d, h, mi


def parse_weekday_tokens(tokens: list[str]) -> Optional[list[int]]:
    if not tokens:
        return []
    low = [t.strip().lower() for t in tokens if t.strip()]
    if not low:
        return []
    if len(low) == 1 and low[0] == "weekdays":
        return [0, 1, 2, 3, 4]
    out: list[int] = []
    for t in low:
        if t not in _WD_MAP:
            return None
        wd = _WD_MAP[t]
        if wd not in out:
            out.append(wd)
    return sorted(out)


def parse_cron_wall_tokens(tokens: list[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Parse args after ``--timestamp`` (lista de tokens sin el flag).
    Retorna (spec_v1 dict, error).
    """
    if not tokens:
        return (
            None,
            (
                "Uso: /crons --timestamp once YYYY-MM-DDTHH:MM · "
                "/crons --timestamp every HH:MM [weekdays|lun mar …]\n"
                "Zona: America/Bogota por defecto (env DUCKCLAW_CRONS_WALL_TZ)."
            ),
        )
    mode = tokens[0].strip().lower()
    tz = default_cron_wall_tz()

    if mode == "once":
        if len(tokens) < 2:
            return None, "Uso: /crons --timestamp once 2026-05-12T14:45"
        dt = parse_once_datetime(tokens[1], tz)
        if not dt:
            return None, "Fecha/hora inválida. Usa 2026-05-12T14:45 o 2026-05-12 14:45"
        y, mo, d, h, mi = dt
        zi = _zone(tz)
        try:
            target = datetime(y, mo, d, h, mi, 0, tzinfo=zi)
        except ValueError:
            return None, "Fecha/hora inválida (calendario)."
        now = datetime.now(zi)
        if target < now.replace(second=0, microsecond=0):
            return None, "La fecha/hora está en el pasado (zona local). Elige un momento futuro."
        spec: dict[str, Any] = {
            "v": CRON_WALL_V1,
            "tz": tz,
            "kind": "once",
            "once_y": y,
            "once_mo": mo,
            "once_d": d,
            "once_h": h,
            "once_mi": mi,
        }
        return spec, None

    if mode == "every":
        if len(tokens) < 2:
            return None, "Uso: /crons --timestamp every 14:45 [weekdays|lun mar mié …]"
        hm = parse_hhmm(tokens[1])
        if not hm:
            return None, "Hora inválida. Usa HH:MM (ej. 09:30)."
        h, mi = hm
        wtoks = tokens[2:]
        weekdays: Optional[list[int]]
        if not wtoks:
            weekdays = []
        else:
            parsed = parse_weekday_tokens(wtoks)
            if parsed is None:
                return None, "Día inválido. Usa weekdays, lun, mar, mié, jue, vie, sab, dom (ES/EN)."
            weekdays = parsed
        spec = {
            "v": CRON_WALL_V1,
            "tz": tz,
            "kind": "every",
            "every_h": h,
            "every_mi": mi,
            "weekdays": weekdays,
        }
        return spec, None

    return None, "Modo inválido. Usa ``once`` o ``every`` después de --timestamp."


def _local_minute_tuple(dt: datetime) -> tuple[int, int, int, int, int]:
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def wall_once_datetime_local(spec: dict[str, Any]) -> Optional[datetime]:
    tz = str(spec.get("tz") or default_cron_wall_tz())
    zi = _zone(tz)
    try:
        return datetime(
            int(spec["once_y"]),
            int(spec["once_mo"]),
            int(spec["once_d"]),
            int(spec["once_h"]),
            int(spec["once_mi"]),
            0,
            tzinfo=zi,
        )
    except (KeyError, TypeError, ValueError):
        return None


def wall_once_expired(spec: dict[str, Any], now_epoch: float) -> bool:
    """True si el slot ``once`` ya no es disparable (pasó el minuto objetivo sin ser el minuto actual)."""
    dt = wall_once_datetime_local(spec)
    if dt is None:
        return True
    zi = dt.tzinfo or _zone(default_cron_wall_tz())
    now_l = datetime.fromtimestamp(now_epoch, tz=zi)

    def _same_minute(a: datetime, b: datetime) -> bool:
        return _local_minute_tuple(a) == _local_minute_tuple(b)

    if _same_minute(now_l, dt):
        return False
    return now_l > dt


def wall_schedule_should_fire(
    now_epoch: float,
    spec: dict[str, Any],
    last_fire_epoch: float,
    poll_s: float,
) -> bool:
    """
    True si toca disparar en este poll. Dedup: no dos veces el mismo minuto local.
    ``poll_s`` se reserva para ventanas futuras; v1 usa igualación por minuto.
    """
    _ = poll_s
    tz_name = str(spec.get("tz") or default_cron_wall_tz())
    zi = _zone(tz_name)
    now_l = datetime.fromtimestamp(now_epoch, tz=zi)
    kind = str(spec.get("kind") or "").strip().lower()

    last_l: Optional[datetime] = None
    if last_fire_epoch and last_fire_epoch > 0:
        try:
            last_l = datetime.fromtimestamp(last_fire_epoch, tz=zi)
        except (OverflowError, OSError, ValueError):
            last_l = None

    def _same_minute(a: datetime, b: datetime) -> bool:
        return _local_minute_tuple(a) == _local_minute_tuple(b)

    if kind == "once":
        target = wall_once_datetime_local(spec)
        if target is None:
            return False
        if not _same_minute(now_l, target):
            return False
        if last_l is not None and _same_minute(last_l, now_l):
            return False
        return True

    if kind == "every":
        try:
            eh = int(spec["every_h"])
            emi = int(spec["every_mi"])
        except (KeyError, TypeError, ValueError):
            return False
        if (now_l.hour, now_l.minute) != (eh, emi):
            return False
        wds = spec.get("weekdays")
        if isinstance(wds, list) and len(wds) > 0:
            if now_l.weekday() not in [int(x) for x in wds]:
                return False
        if last_l is not None and _same_minute(last_l, now_l):
            return False
        return True

    return False


def format_cron_wall_human(spec: dict[str, Any]) -> str:
    try:
        tz = str(spec.get("tz") or default_cron_wall_tz())
        kind = str(spec.get("kind") or "")
        if kind == "once":
            return (
                f"Horario de reloj (una vez): "
                f"{int(spec['once_y']):04d}-{int(spec['once_mo']):02d}-{int(spec['once_d']):02d} "
                f"{int(spec['once_h']):02d}:{int(spec['once_mi']):02d} ({tz})"
            )
        if kind == "every":
            h, mi = int(spec["every_h"]), int(spec["every_mi"])
            wds = spec.get("weekdays")
            if isinstance(wds, list) and len(wds) > 0:
                return f"Horario de reloj: cada {h:02d}:{mi:02d} ({tz}) días {list(wds)}"
            return f"Horario de reloj: cada día a {h:02d}:{mi:02d} ({tz})"
    except (KeyError, TypeError, ValueError):
        pass
    return "Horario de reloj (configuración presente)."
