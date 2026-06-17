"""Legacy facade for homeostasis notification helpers.

The implementation is owned by :mod:`duckclaw.homeostasis.notify`.
Keep this module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis.notify import notify_ask_task

__all__ = ["notify_ask_task"]
