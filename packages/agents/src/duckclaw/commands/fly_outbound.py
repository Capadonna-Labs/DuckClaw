"""Cola FIFO de gráficos PNG base64 por sesión chat (outbound Telegram)."""

from __future__ import annotations

from typing import Any

# Cola FIFO de PNG base64 por chat: api-gateway hace pop_all y sendPhoto en orden.
_FLY_OUTBOUND_CHART_B64: dict[str, list[str]] = {}

_FLY_OUTBOUND_CHART_NAMES: dict[str, list[str]] = {}


def register_fly_outbound_chart_b64(
    session_id: Any, b64: str, *, chart_name: str | None = None
) -> None:
    s = (b64 or "").strip()
    if not s:
        return
    k = str(session_id).strip()
    _FLY_OUTBOUND_CHART_B64.setdefault(k, []).append(s)
    if chart_name and str(chart_name).strip():
        _FLY_OUTBOUND_CHART_NAMES.setdefault(k, []).append(str(chart_name).strip())


def pop_all_fly_outbound_charts(session_id: Any) -> tuple[list[str], list[str]]:
    """Devuelve y vacía figuras encoladas (b64, nombres legibles) en orden FIFO."""
    k = str(session_id).strip()
    charts_b64 = _FLY_OUTBOUND_CHART_B64.pop(k, [])
    chart_names = _FLY_OUTBOUND_CHART_NAMES.pop(k, [])
    while len(chart_names) < len(charts_b64):
        chart_names.append(f"chart-{len(chart_names) + 1}.png")
    return charts_b64, chart_names


def pop_all_fly_outbound_charts_b64(session_id: Any) -> list[str]:
    """Devuelve y vacía todas las figuras encoladas para este chat (orden FIFO)."""
    charts_b64, _ = pop_all_fly_outbound_charts(session_id)
    return charts_b64


def pop_fly_outbound_chart_b64(session_id: Any) -> str | None:
    """Compat: saca solo el primer PNG de la cola; preferir pop_all en el gateway."""
    k = str(session_id).strip()
    q = _FLY_OUTBOUND_CHART_B64.get(k)
    if not q:
        return None
    first = q.pop(0)
    if not q:
        del _FLY_OUTBOUND_CHART_B64[k]
    return first
