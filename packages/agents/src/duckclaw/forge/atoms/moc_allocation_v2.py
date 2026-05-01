"""Válvula MOC v2: CFD + régimen PGQ + perfil VSS."""

from __future__ import annotations

from typing import Any

from duckclaw.forge.models.core_satellite import MOCTargetAllocationV2

_VALVULA_MAP = {
    "GAS": 1.0,
    "LIQUID": 0.7,
    "SOLID": 0.4,
    "PLASMA": 0.0,
}

_RISK_MULT = {
    "conservative": 0.6,
    "medium": 1.0,
    "aggressive": 1.3,
}


def calculate_target_allocation_v2(
    ticker: str,
    fase_fluido: str,
    hrp_weight_capped: float,
    equity: float,
    posicion_actual_usd: float,
    regime: dict[str, Any],
    investor_profile: dict[str, Any],
) -> dict[str, object]:
    tk = (ticker or "").strip().upper()
    ff = (fase_fluido or "").strip().upper() or "SOLID"
    valvula_base = float(_VALVULA_MAP.get(ff, 0.0))
    hrp = max(0.0, float(hrp_weight_capped))
    eq = max(0.0, float(equity))
    pos_usd = float(posicion_actual_usd)

    excluded = {str(x).strip().upper() for x in (investor_profile.get("excluded_tickers") or []) if x}
    if tk in excluded:
        return MOCTargetAllocationV2(
            action="SKIP",
            delta_usd=0.0,
            fase=ff,
            regime_tag=str(regime.get("regime") or ""),
            rationale=f"{tk} excluido por perfil de inversión",
        ).as_dict()

    reg_name = str(regime.get("regime") or "DESCONOCIDO").strip().upper()
    conf = 0.0
    try:
        conf = float(regime.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    coherent = {str(x).strip().upper() for x in (regime.get("coherent_assets") or [])}
    contras = {str(x).strip().upper() for x in (regime.get("contraindicated_assets") or [])}

    macro_penalty = 1.0
    macro_bonus = 1.0
    if reg_name == "DESCONOCIDO" or conf <= 0.0:
        macro_penalty = 1.0
        macro_bonus = 1.0
    else:
        if tk in contras:
            macro_penalty = 0.3 if conf >= 0.7 else 0.6
        if tk in coherent:
            macro_bonus = 1.2

    risk_tol = str(investor_profile.get("risk_tolerance") or "medium").strip().lower()
    risk_mult = float(_RISK_MULT.get(risk_tol, 1.0))

    prod = valvula_base * macro_penalty * macro_bonus * risk_mult
    prod = max(0.0, min(1.0, prod))

    target_weight = min(hrp, hrp * prod)
    target_capital = eq * target_weight if eq > 0 else 0.0
    delta_capital = target_capital - pos_usd
    equity_abs = abs(eq)
    delta_pct = (abs(delta_capital) / equity_abs * 100.0) if equity_abs > 1e-12 else 0.0

    threshold_pct = 1.0
    threshold_abs = 500.0

    if delta_pct < threshold_pct and abs(delta_capital) < threshold_abs:
        return MOCTargetAllocationV2(
            action="HOLD",
            delta_usd=float(delta_capital),
            target_weight=target_weight,
            hrp_weight=hrp,
            valvula_base=valvula_base,
            valvula_final=prod,
            valvula=prod,
            macro_penalty=macro_penalty,
            macro_bonus=macro_bonus,
            risk_multiplier=risk_mult,
            fase=ff,
            regime_tag=reg_name,
            rationale=f"Delta {delta_pct:.2f}% < threshold",
        ).as_dict()

    signal = "BUY" if delta_capital > 0 else "SELL"

    rationale = (
        f"HRP cap: {hrp:.1%} | CFD {ff}: válvula {valvula_base:.0%} | "
        f"Macro {reg_name}: penalización ×{macro_penalty:.1f} bonificación ×{macro_bonus:.1f} | "
        f"Perfil riesgo ×{risk_mult:.1f} | Válvula final: {prod:.1%} | "
        f"Delta: ${delta_capital:+,.0f}"
    )

    return MOCTargetAllocationV2(
        action=signal,
        delta_usd=float(delta_capital),
        target_weight=target_weight,
        hrp_weight=hrp,
        valvula_base=valvula_base,
        valvula_final=prod,
        valvula=prod,
        macro_penalty=macro_penalty,
        macro_bonus=macro_bonus,
        risk_multiplier=risk_mult,
        fase=ff,
        regime_tag=reg_name,
        rationale=rationale,
    ).as_dict()
