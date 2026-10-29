"""Per-turn LLM spend cap: a runaway agent loop is an outage with an invoice.

``track_turn_spend()`` opens a box for one turn; every LLM call charges it and the next call raises ``TurnBudgetExceeded``
once the box reaches ``DUCKCLAW_TURN_BUDGET_USD`` (default 0.50, <= 0 turns it off). The box is a mutable list in a
ContextVar, so it survives ``copy_context()`` into the delegate thread pool and into asyncio tasks.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_spent: ContextVar[list[float] | None] = ContextVar("duckclaw_turn_spend_usd", default=None)


class TurnBudgetExceeded(RuntimeError):
    pass


def turn_budget_usd() -> float:
    try:
        return float(os.environ.get("DUCKCLAW_TURN_BUDGET_USD") or "0.50")
    except ValueError:
        return 0.50


@contextmanager
def track_turn_spend() -> Iterator[list[float]]:
    box = [0.0]
    token = _spent.set(box)
    try:
        yield box
    finally:
        _spent.reset(token)


def charge_turn_spend(usd: float) -> None:
    box = _spent.get()
    if box is not None:
        box[0] += max(0.0, usd)  # ponytail: unlocked += across delegate threads; a lost update is a few cents, lock if it ever matters


def check_turn_budget() -> None:
    box, cap = _spent.get(), turn_budget_usd()
    if box is not None and 0 < cap <= box[0]:
        raise TurnBudgetExceeded(f"turn halted: estimated spend ${box[0]:.4f} reached the ${cap:.2f} cap (DUCKCLAW_TURN_BUDGET_USD)")
