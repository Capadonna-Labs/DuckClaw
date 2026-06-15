"""Legacy facade for transversal goals alignment.

The implementation is owned by :mod:`duckclaw.homeostasis.goals_alignment`.
Keep this module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.homeostasis.goals_alignment import (
    GOALS_ALIGNMENT_REVIEW_PHRASE,
    AlignmentItem,
    AlignmentReport,
    alignment_review_phrase_in_text,
    assess_goals_alignment,
    assess_goals_list_alignment,
    build_alignment_nudge_system_event,
    normalize_jitter_ratio,
    normalize_notify_channel,
    normalize_proactive_mode,
    pick_nudge_opener,
    refresh_goal_observations,
    refresh_goals_list_observations,
)

__all__ = [
    "GOALS_ALIGNMENT_REVIEW_PHRASE",
    "AlignmentItem",
    "AlignmentReport",
    "alignment_review_phrase_in_text",
    "assess_goals_alignment",
    "assess_goals_list_alignment",
    "build_alignment_nudge_system_event",
    "normalize_jitter_ratio",
    "normalize_notify_channel",
    "normalize_proactive_mode",
    "pick_nudge_opener",
    "refresh_goal_observations",
    "refresh_goals_list_observations",
]
