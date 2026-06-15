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
