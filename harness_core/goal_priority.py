"""Priority ordering for homeostasis domain goals (lower number = attend first)."""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")

_DEFAULT_PRIORITY = 100


def parse_goal_priority(raw: Any, *, default: int = _DEFAULT_PRIORITY) -> int:
    """Normalize priority; invalid/missing → default (100). Must be >= 1."""
    if raw is None:
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return v if v >= 1 else default


def goal_priority_label(goal: Any) -> str:
    """Human label P{n} for listings and agent directives."""
    if isinstance(goal, dict):
        p = parse_goal_priority(goal.get("priority"))
        key = (goal.get("belief_key") or "").strip()
    else:
        p = parse_goal_priority(getattr(goal, "priority", None))
        key = (getattr(goal, "belief_key", None) or "").strip()
    if p >= _DEFAULT_PRIORITY and not key:
        return ""
    return f"P{p}"


def goal_priority_display(goal: Any, *, rank: int) -> str:
    """P{n} for /goals listing: stored priority if set, else 1-based rank in sorted list."""
    if isinstance(goal, dict):
        stored = parse_goal_priority(goal.get("priority"))
    else:
        stored = parse_goal_priority(getattr(goal, "priority", None))
    if stored < _DEFAULT_PRIORITY:
        return f"P{stored}"
    return f"P{rank}"


def _belief_key_for_sort(goal: Any) -> str:
    if isinstance(goal, dict):
        return (goal.get("belief_key") or "").strip().lower()
    return (getattr(goal, "belief_key", None) or "").strip().lower()


def sort_goals_by_priority(goals: list[T]) -> list[T]:
    """Stable sort: priority ascending (1 before 2), then manifest list order."""
    indexed = list(enumerate(goals or []))
    return [
        g
        for _, g in sorted(
            indexed,
            key=lambda pair: (parse_goal_priority(_priority_raw(pair[1])), pair[0]),
        )
    ]


def _priority_raw(goal: Any) -> Any:
    if isinstance(goal, dict):
        return goal.get("priority")
    return getattr(goal, "priority", None)


def next_goal_priority(existing: list[Any]) -> int:
    """Next priority for a newly added goal (max + 1, or 1 if empty)."""
    if not existing:
        return 1
    return max(parse_goal_priority(_priority_raw(g)) for g in existing) + 1


def assign_sequential_priorities(goals: list[T], *, start: int = 1) -> list[T]:
    """Assign 1..n priorities in list order (migrate / backfill)."""
    out: list[T] = []
    p = start
    for g in goals or []:
        if isinstance(g, dict):
            row = dict(g)
            if parse_goal_priority(row.get("priority"), default=_DEFAULT_PRIORITY) >= _DEFAULT_PRIORITY:
                row["priority"] = p
            out.append(row)  # type: ignore[misc]
        elif hasattr(g, "model_copy"):
            cur = parse_goal_priority(getattr(g, "priority", None))
            if cur >= _DEFAULT_PRIORITY:
                out.append(g.model_copy(update={"priority": p}))
            else:
                out.append(g)
        else:
            out.append(g)
        p += 1
    return out
