"""Tool always-on: espera bloqueante dentro del turno (await / sleep)."""

from __future__ import annotations

import json
import re
import time
from typing import Any, List

from langchain_core.tools import StructuredTool

# Techo duro: no colgar el graph/worker en esperas largas.
# Para demoras > MAX usa configure_loop_homeostasis / crons (próximo tick).
DEFAULT_MAX_SECONDS = 120.0
DEFAULT_MIN_SECONDS = 0.1

_DURATION_RE = re.compile(
    r"^\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>ms|s|sec|secs|seconds|m|min|mins|minutes)?\s*$",
    re.IGNORECASE,
)


def parse_await_duration(raw: Any, *, default_unit: str = "s") -> tuple[float | None, str | None]:
    """Parsea segundos desde número o string ('5', '5s', '250ms', '2m')."""
    if raw is None:
        return None, "seconds_required"
    if isinstance(raw, bool):
        return None, "seconds_invalid"
    if isinstance(raw, (int, float)):
        secs = float(raw)
        if secs != secs:  # NaN
            return None, "seconds_invalid"
        return secs, None
    text = str(raw).strip()
    if not text:
        return None, "seconds_required"
    m = _DURATION_RE.match(text)
    if not m:
        return None, "seconds_unparseable"
    value = float(m.group("value").replace(",", "."))
    unit = (m.group("unit") or default_unit).lower()
    if unit in ("ms",):
        return value / 1000.0, None
    if unit in ("s", "sec", "secs", "seconds"):
        return value, None
    if unit in ("m", "min", "mins", "minutes"):
        return value * 60.0, None
    return None, "seconds_unparseable"


def clamp_await_seconds(
    seconds: float,
    *,
    min_seconds: float = DEFAULT_MIN_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> tuple[float, bool]:
    """Devuelve (segundos_efectivos, fue_capado)."""
    capped = False
    out = float(seconds)
    if out < min_seconds:
        out = min_seconds
        capped = True
    if out > max_seconds:
        out = max_seconds
        capped = True
    return out, capped


def await_interval_impl(
    seconds: Any,
    reason: str = "",
    *,
    min_seconds: float = DEFAULT_MIN_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    sleeper: Any = time.sleep,
) -> str:
    """Espera `seconds` (bloqueante) y devuelve JSON con lo dormido."""
    parsed, err = parse_await_duration(seconds)
    if err or parsed is None:
        return json.dumps(
            {
                "status": "error",
                "error": err or "seconds_invalid",
                "hint": "Pasa un número (p. ej. 5) o duración ('5s', '500ms', '2m'). Máx "
                f"{max_seconds:g}s por llamada.",
            },
            ensure_ascii=False,
        )
    if parsed <= 0:
        return json.dumps(
            {
                "status": "error",
                "error": "seconds_must_be_positive",
                "requested_seconds": parsed,
            },
            ensure_ascii=False,
        )
    effective, capped = clamp_await_seconds(
        parsed, min_seconds=min_seconds, max_seconds=max_seconds
    )
    t0 = time.monotonic()
    sleeper(effective)
    slept = time.monotonic() - t0
    out: dict[str, Any] = {
        "status": "ok",
        "requested_seconds": parsed,
        "slept_seconds": round(slept, 3),
        "effective_seconds": effective,
        "capped": capped,
        "max_seconds": max_seconds,
    }
    note = (reason or "").strip()
    if note:
        out["reason"] = note[:240]
    if capped and parsed > max_seconds:
        out["note"] = (
            f"Capado a {max_seconds:g}s. Para esperas más largas usa "
            "configure_loop_homeostasis o un cron/wall schedule (próximo tick), "
            "no bloquees el turno."
        )
    return json.dumps(out, ensure_ascii=False)


def register_await_interval_skill(tools_list: List[Any], db: Any = None) -> None:
    """Registra ``await_interval`` (espera con techo duro dentro del turno)."""
    del db  # API simétrica a otros bridges; no necesita DB.

    def await_interval(seconds: float, reason: str = "") -> str:
        """
        Espera bloqueante dentro del turno actual (pausa entre pasos/tools).

        seconds: duración en segundos (número) o string ('5s', '500ms', '2m').
        Máximo 120s por llamada. Para demoras largas / periódicas usa
        configure_loop_homeostasis o crons en Heartbeat, no esta tool.
        reason: opcional, se refleja en el resultado JSON.
        """
        return await_interval_impl(seconds, reason)

    tools_list.append(
        StructuredTool.from_function(
            await_interval,
            name="await_interval",
            description=(
                "Pausa el turno N segundos entre pasos (poll, rate-limit, dar tiempo a un sistema). "
                "seconds: número o '5s'/'500ms'/'2m'. Máx 120s por llamada. "
                "Para esperas largas o periódicas usa configure_loop_homeostasis / crons, no esta tool."
            ),
        )
    )
