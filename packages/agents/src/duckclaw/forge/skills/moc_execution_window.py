"""Ventana MOC (America/Bogota) para propose + auto-exec y ancla CONTEXT.

Un solo formato de env (`DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW`) comparte
`quant_trader_bridge` y el gateway (mensajes SUMMARIZE /context).

Formato: ``HH:MM[:SS]-HH:MM[:SS]`` (segundos opcionales; default 14:40:00–14:59:30 COT).

Comparación por segundos desde medianoche inclusiva en ambos extremos.
"""

from __future__ import annotations

import os
import re
from typing import Mapping

_MOC_WIN_RE = re.compile(
    r"^\s*"
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2})(?::(?P<ss>\d{2}))?\s*-\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2})(?::(?P<es>\d{2}))?"
    r"\s*$"
)

_RAW_DEF_DEFAULT = "14:40:00-14:59:30"


def _hms_totuple(h: int, m: int, s: int) -> tuple[bool, tuple[int, int, int]]:
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
        return False, (0, 0, 0)
    return True, (h, m, s)


def _to_sec(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


def _fmt_boundary(sec: int) -> str:
    sec = max(0, min(86399, sec))
    h, rem = sec // 3600, sec % 3600
    m, s = rem // 60, rem % 60
    if s == 0:
        return f"{h:02d}:{m:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_moc_execution_window_bounds(
    environ: Mapping[str, str] | None = None,
) -> tuple[int, int, str]:
    """
    Devuelve (start_sec_since_midnight_cot, end_sec_since_midnight_cot, etiqueta_visual).

    Inclusivo en inicio y fin (p. ej. 14:59:30 permite hasta ese segundo inclusive).
    """
    env = environ if environ is not None else os.environ

    def _fallback() -> tuple[int, int, str]:
        s, e = _to_sec(14, 40, 0), _to_sec(14, 59, 30)
        return s, e, f"{_fmt_boundary(s)}-{_fmt_boundary(e)}"

    raw = (env.get("DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW") or "").strip()
    candidate = raw if raw else _RAW_DEF_DEFAULT
    m = _MOC_WIN_RE.match(candidate) or _MOC_WIN_RE.match(_RAW_DEF_DEFAULT)
    if not m:
        return _fallback()

    sh, sm = int(m.group("sh")), int(m.group("sm"))
    ss = int(m.group("ss") or 0)
    eh, em = int(m.group("eh")), int(m.group("em"))
    es = int(m.group("es") or 0)

    ok_s, t_s = _hms_totuple(sh, sm, ss)
    ok_e, t_e = _hms_totuple(eh, em, es)
    if not (ok_s and ok_e):
        return _fallback()

    s_sec = _to_sec(*t_s)
    e_sec = _to_sec(*t_e)
    if s_sec > e_sec:
        return _fallback()

    return s_sec, e_sec, f"{_fmt_boundary(s_sec)}-{_fmt_boundary(e_sec)}"
