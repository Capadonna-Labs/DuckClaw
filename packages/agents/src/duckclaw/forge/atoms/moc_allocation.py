"""
Fusión Mandato HRP + fase CFD (válvula MOC).

Función pura testeable sin I/O — spec Core-Satellite.
"""

from __future__ import annotations

from duckclaw.forge.models.core_satellite import TargetAllocationDict


_VALVULA_MAP = {
    "GAS": 1.0,
    "LIQUID": 0.7,
    "SOLID": 0.4,
    "PLASMA": 0.0,
}


def calculate_target_allocation(
    ticker: str,
    fase_fluido: str,
    hrp_weight_capped: float,
    equity: float,
    posicion_actual_usd: float,
) -> dict[str, object]:
    """
    Fusiona límite estructural HRP con momentum CFD.

    ticker: etiqueta humana opcional para racional (no usa lógica adicional aquí).
    """
    del ticker
    ff = (fase_fluido or "").strip().upper()
    valvula = float(_VALVULA_MAP.get(ff, 0.0))

    target_weight = float(hrp_weight_capped) * valvula
    target_capital = float(equity) * target_weight if equity > 0 else 0.0
    delta_capital = target_capital - float(posicion_actual_usd)
    equity_abs = abs(float(equity))
    delta_pct = (abs(delta_capital) / equity_abs * 100.0) if equity_abs > 1e-12 else 0.0

    threshold_pct = 1.0
    threshold_abs = 500.0

    if delta_pct < threshold_pct and abs(delta_capital) < threshold_abs:
        return TargetAllocationDict(
            action="HOLD",
            delta_usd=float(delta_capital),
            rationale=f"Delta {delta_pct:.2f}% < threshold",
        ).as_dict()

    signal = "BUY" if delta_capital > 0 else "SELL"

    rationale = (
        f"HRP cap: {hrp_weight_capped:.1%} | "
        f"Válvula {ff}: {valvula:.0%} | "
        f"Target: {target_weight:.1%} | "
        f"Delta: ${delta_capital:+,.0f}"
    )

    return TargetAllocationDict(
        action=signal if signal in ("BUY", "SELL") else "HOLD",
        delta_usd=float(delta_capital),
        target_weight=target_weight,
        hrp_weight=float(hrp_weight_capped),
        valvula=valvula,
        fase=ff,
        rationale=rationale,
    ).as_dict()
