"""Legacy facade for the transversal homeostasis manager.

The implementation is owned by :mod:`duckclaw.homeostasis.manager`.
Keep this module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis.manager import HomeostasisManager

__all__ = ["HomeostasisManager"]
