"""SurpriseCalculator — define qué constituye una anomalía en el dominio del agente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class SurpriseResult:
    """Resultado del cálculo de sorpresa."""

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
    """
    Calcula sorpresa.
    - symmetric: delta = |observed - target|; anomalía si delta > threshold.
    - ceiling: techo en target (p. ej. DD máximo permitido); anomalía si observed > target + threshold;
 delta = max(0, observed - target).

    Args:
        observed: Valor percibido del entorno.
        target: Valor esperado (creencia).
        threshold: Umbral de tolerancia o banda por encima del techo.
        comparison: symmetric | ceiling

    Returns:
        SurpriseResult con delta, is_anomaly, etc.
    """
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
    """Calcula sorpresa comparando percepción con creencias."""

    @staticmethod
    def compute(
        observed: float,
        target: float,
        threshold: float,
        *,
        comparison: str = "symmetric",
    ) -> SurpriseResult:
        """Alias para compute_surprise."""
        return compute_surprise(observed, target, threshold, comparison=comparison)
