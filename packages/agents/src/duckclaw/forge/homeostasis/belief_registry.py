"""Legacy facade for transversal belief registry.

The implementation is owned by :mod:`duckclaw.homeostasis.belief_registry`.
Keep this module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis.belief_registry import (
    Belief,
    BeliefRegistry,
    RestorationAction,
    load_beliefs_from_config,
)

__all__ = ["Belief", "BeliefRegistry", "RestorationAction", "load_beliefs_from_config"]
