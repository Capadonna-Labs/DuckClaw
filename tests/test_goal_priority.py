"""Tests for goal priority ordering."""

from __future__ import annotations

from harness_core.goal_priority import (
    assign_sequential_priorities,
    goal_priority_label,
    next_goal_priority,
    parse_goal_priority,
    sort_goals_by_priority,
)
from harness_core.states.loop_state import DomainGoal


def test_parse_goal_priority_defaults() -> None:
    assert parse_goal_priority(None) == 100
    assert parse_goal_priority("bad") == 100
    assert parse_goal_priority(0) == 100
    assert parse_goal_priority(2) == 2


def test_sort_goals_by_priority_ascending() -> None:
    goals = [
        {"belief_key": "b", "priority": 2},
        {"belief_key": "a", "priority": 1},
    ]
    sorted_goals = sort_goals_by_priority(goals)
    assert [g["belief_key"] for g in sorted_goals] == ["a", "b"]


def test_sort_preserves_manifest_order_on_tie() -> None:
    goals = [
        {"belief_key": "first", "priority": 100},
        {"belief_key": "second", "priority": 100},
    ]
    sorted_goals = sort_goals_by_priority(goals)
    assert [g["belief_key"] for g in sorted_goals] == ["first", "second"]


def test_next_goal_priority() -> None:
    goals = [
        DomainGoal(belief_key="a", target_value=0, threshold=0, title="A", priority=1),
        DomainGoal(belief_key="b", target_value=0, threshold=0, title="B", priority=3),
    ]
    assert next_goal_priority(goals) == 4


def test_assign_sequential_priorities_backfills_default() -> None:
    goals = [
        DomainGoal(belief_key="a", target_value=0, threshold=0, title="A"),
        DomainGoal(belief_key="b", target_value=0, threshold=0, title="B", priority=5),
    ]
    out = assign_sequential_priorities(goals)
    assert out[0].priority == 1
    assert out[1].priority == 5


def test_goal_priority_label() -> None:
    assert goal_priority_label({"belief_key": "x", "priority": 2}) == "P2"


def test_goal_priority_display_uses_rank_when_unset() -> None:
    from harness_core.goal_priority import goal_priority_display

    g = DomainGoal(belief_key="a", target_value=0, threshold=0, title="A")
    assert goal_priority_display(g, rank=1) == "P1"
    g2 = DomainGoal(belief_key="b", target_value=0, threshold=0, title="B", priority=2)
    assert goal_priority_display(g2, rank=2) == "P2"
