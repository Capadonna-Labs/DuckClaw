"""Atajos de teclado para el chat TUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.key_binding import KeyBindings

from duckops.sovereign.workers_catalog import WorkerPick


@dataclass
class WorkerTabCycle:
    picks: list[WorkerPick]
    index: int = 0

    def current_worker_id(self, fallback: str) -> str:
        if not self.picks:
            return fallback
        idx = self.index % len(self.picks)
        return self.picks[idx].worker_id


def build_chat_key_bindings(
    cycle: WorkerTabCycle,
    *,
    on_worker_change: Callable[[str], None],
) -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("tab")
    def _next_worker(event) -> None:
        if not cycle.picks:
            return
        cycle.index = (cycle.index + 1) % len(cycle.picks)
        wid = cycle.current_worker_id("")
        on_worker_change(wid)

    @bindings.add("s-tab")
    def _prev_worker(event) -> None:
        if not cycle.picks:
            return
        cycle.index = (cycle.index - 1) % len(cycle.picks)
        wid = cycle.current_worker_id("")
        on_worker_change(wid)

    return bindings
