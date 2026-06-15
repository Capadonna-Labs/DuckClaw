"""Transversal belief registry for homeostasis checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Belief:
    """A numeric belief target and tolerance band."""

    key: str
    target: float
    threshold: float
    comparison: str = "symmetric"


@dataclass
class RestorationAction:
    """Action metadata to use when a belief is anomalous."""

    trigger: str
    skill: str
    message: str


def load_beliefs_from_config(config: dict[str, Any] | None) -> tuple[list[Belief], dict[str, RestorationAction]]:
    """Parse a homeostasis config dict into beliefs and restoration actions."""
    beliefs: list[Belief] = []
    actions: dict[str, RestorationAction] = {}
    if not config or not isinstance(config, dict):
        return beliefs, actions

    for b in config.get("beliefs") or []:
        if isinstance(b, dict) and b.get("key"):
            try:
                target = float(b.get("target", 0))
                threshold = float(b.get("threshold", 0))
                comp_raw = str(b.get("comparison") or "symmetric").strip().lower()
                comparison = comp_raw if comp_raw in ("symmetric", "ceiling") else "symmetric"
                beliefs.append(
                    Belief(key=str(b["key"]).strip(), target=target, threshold=threshold, comparison=comparison)
                )
            except (TypeError, ValueError):
                pass

    for a in config.get("actions") or []:
        if isinstance(a, dict) and a.get("trigger"):
            trigger = str(a["trigger"]).strip()
            skill = str(a.get("skill") or "").strip()
            message = str(a.get("message") or "").strip()
            actions[trigger] = RestorationAction(trigger=trigger, skill=skill, message=message)

    return beliefs, actions


class BeliefRegistry:
    """Registry of worker belief targets."""

    def __init__(self, beliefs: list[Belief], actions: dict[str, RestorationAction]):
        self.beliefs = beliefs
        self.actions = actions

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "BeliefRegistry":
        """Create a registry from a homeostasis config dict."""
        beliefs, actions = load_beliefs_from_config(config)
        return cls(beliefs=beliefs, actions=actions)

    def get_belief(self, key: str) -> Belief | None:
        """Return a belief by key."""
        for b in self.beliefs:
            if b.key == key:
                return b
        return None

    def get_action_for_trigger(self, trigger: str) -> RestorationAction | None:
        """Return a restoration action by trigger name."""
        return self.actions.get(trigger)

    def trigger_for_belief(self, belief_key: str, is_drop: bool = True) -> str:
        """Build the conventional trigger name for a belief anomaly."""
        suffix = "drop" if is_drop else "breach"
        return f"{belief_key}_{suffix}"
