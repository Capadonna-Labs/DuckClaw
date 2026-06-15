"""Legacy facade for transversal surprise calculation.

The implementation is owned by :mod:`duckclaw.homeostasis.surprise`.
Keep this module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis.surprise import SurpriseCalculator, SurpriseResult, compute_surprise

__all__ = ["SurpriseCalculator", "SurpriseResult", "compute_surprise"]
