"""Transversal surprise calculation for homeostasis checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SurpriseResult:
    """Result of comparing an observed value against a target band."""

    delta: float
    is_anomaly: bool
    target: float
    observed: float
    threshold: float
    scale_mismatch: bool = False


def detect_value_scale_mismatch(
    observed: float,
    target: float,
    threshold: float,
    *,
    value_unit: str | None = None,
) -> bool:
    """True when observed and target appear to use incompatible numeric scales."""
    o = abs(float(observed))
    t = abs(float(target))
    th = abs(float(threshold))
    unit = (value_unit or "").strip().lower()
    if unit == "percent":
        # ponytail: |obs| > 100 usually means absolute units, not percent
        return o > max(100.0, 10.0 * (t + th + 1.0))
    if unit == "absolute":
        return False
    # Heuristic: small percent-like target (<=100) vs order-of-magnitude larger observed
    if 0 < t <= 100 and th <= t and o > 10.0 * max(t + th, 1.0):
        return True
    return False


def compute_surprise(
    observed: float,
    target: float,
    threshold: float,
    *,
    comparison: str = "symmetric",
) -> SurpriseResult:
    """Compute whether an observed value is outside its tolerated target band."""
    comp = (comparison or "symmetric").strip().lower()
    if comp == "ceiling":
        delta = max(0.0, float(observed) - float(target))
        is_anomaly = float(observed) > float(target) + float(threshold)
    else:
        delta = abs(float(observed) - float(target))
        is_anomaly = delta > float(threshold)
    return SurpriseResult(
        delta=delta,
        is_anomaly=is_anomaly,
        target=target,
        observed=observed,
        threshold=threshold,
    )


class SurpriseCalculator:
    """Compatibility wrapper for callers that use a class-based API."""

    @staticmethod
    def compute(
        observed: float,
        target: float,
        threshold: float,
        *,
        comparison: str = "symmetric",
    ) -> SurpriseResult:
        """Alias for compute_surprise."""
        return compute_surprise(observed, target, threshold, comparison=comparison)
