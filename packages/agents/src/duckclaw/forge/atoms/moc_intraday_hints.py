"""
Fusiona hints de quant_core.intraday_moc_accum con la salida de la válvula MOC.

Mandato HRP (`hrp_weight_capped`) sigue siendo techo absoluto sobre `target_weight`.
Spec: specs/features/Core-Satellite HRP Weekly + MOC CFD.md
"""

from __future__ import annotations

import json
from typing import Any

from duckclaw.forge.models.core_satellite import TargetAllocationDict

_THRESHOLD_PCT = 1.0
_THRESHOLD_ABS = 500.0


def merge_intraday_accum_payload(existing: Any, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge superficial; `patch` pisa claves de primer nivel."""
    base: dict[str, Any] = {}
    if existing is not None:
        try:
            if isinstance(existing, str) and existing.strip():
                parsed = json.loads(existing)
                if isinstance(parsed, dict):
                    base = dict(parsed)
            elif isinstance(existing, dict):
                base = dict(existing)
        except (json.JSONDecodeError, TypeError):
            base = {}
    merged: dict[str, Any] = {**base, **patch}
    return merged


def apply_intraday_accum_hints_to_allocation(
    tgt: dict[str, Any],
    hints: dict[str, Any] | None,
    *,
    hrp_weight_capped: float,
    equity: float,
    posicion_actual_usd: float,
) -> dict[str, Any]:
    """
    Modifica resultado de válvula (v1/v2) con hints intradía.

    Claves soportadas en `hints`:
    - ``weight_scale`` (float): multiplica ``target_weight`` previo del dict; clamp a [hrp_techo].
    - ``force_hold`` (truthy): fuerza HOLD (sin crear señal MOC sobre ese ticker en la práctica).
    """
    if not hints:
        return dict(tgt)
    out = dict(tgt)

    force_hold_keys = hints.get("force_hold")
    if force_hold_keys in (True, 1, "1", "true", "TRUE", "yes"):
        return TargetAllocationDict(
            action="HOLD",
            delta_usd=float(out.get("delta_usd") or 0.0),
            target_weight=out.get("target_weight"),
            hrp_weight=out.get("hrp_weight"),
            valvula=out.get("valvula"),
            fase=str(out.get("fase") or ""),
            rationale=(str(out.get("rationale") or "") + " · intraday force_hold"),
        ).as_dict()

    try:
        scale = float(hints.get("weight_scale") or 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    scale_max = float(hints.get("weight_scale_max") or 3.0)
    scale = max(0.0, min(scale, scale_max))

    tw0 = float(out.get("target_weight") or 0.0)
    cap = max(0.0, float(hrp_weight_capped))
    tw = min(cap, tw0 * scale)
    ff = str(out.get("fase") or "").strip().upper()
    rationale_extra = ""
    notes = hints.get("notes")
    if isinstance(notes, str) and notes.strip():
        rationale_extra = " · intraday_notes: " + notes.strip()[:200]

    target_capital = float(equity) * tw if equity > 0 else 0.0
    delta_capital = target_capital - float(posicion_actual_usd)
    equity_abs = abs(float(equity))
    delta_pct = (abs(delta_capital) / equity_abs * 100.0) if equity_abs > 1e-12 else 0.0

    if delta_pct < _THRESHOLD_PCT and abs(delta_capital) < _THRESHOLD_ABS:
        return TargetAllocationDict(
            action="HOLD",
            delta_usd=float(delta_capital),
            target_weight=tw,
            hrp_weight=out.get("hrp_weight"),
            valvula=out.get("valvula"),
            fase=ff,
            rationale=f"Delta {delta_pct:.2f}% tras hints intradía < threshold{rationale_extra}",
        ).as_dict()

    signal = "BUY" if delta_capital > 0 else "SELL"
    rationale = (
        str(out.get("rationale") or "")
        + f" · intraday weight_scale={scale:.3f}, target_tw={tw:.3f}{rationale_extra}"
    )
    return TargetAllocationDict(
        action=signal,
        delta_usd=float(delta_capital),
        target_weight=tw,
        hrp_weight=float(cap) if out.get("hrp_weight") is not None else float(hrp_weight_capped),
        valvula=out.get("valvula"),
        fase=ff,
        rationale=rationale.strip(" ·") or rationale,
    ).as_dict()
