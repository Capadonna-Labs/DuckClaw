"""Legacy facade for homeostasis public contracts.

The implementation is owned by :mod:`duckclaw.homeostasis`.
Keep this package as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis import (
    Belief,
    BeliefRegistry,
    HomeostasisManager,
    RestorationAction,
    SurpriseCalculator,
    SurpriseResult,
    compute_surprise,
    load_beliefs_from_config,
)

__all__ = [
    "Belief",
    "BeliefRegistry",
    "RestorationAction",
    "load_beliefs_from_config",
    "SurpriseCalculator",
    "SurpriseResult",
    "compute_surprise",
    "HomeostasisManager",
]
