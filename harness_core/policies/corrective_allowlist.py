"""Zero-trust validation for meditate corrective actions."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from harness_core.states.meditate_state import CorrectiveAction, CorrectiveActionType

_log = logging.getLogger(__name__)

SAFE_AUTO_ACTION_TYPES: frozenset[CorrectiveActionType] = frozenset(
    {"purge_stale_tasks", "quarantine_corrupted_memory", "noop"}
)
HITL_ACTION_TYPES: frozenset[CorrectiveActionType] = frozenset(
    {"request_compaction", "alert_admin", "circuit_breaker_pause"}
)

_ALLOWED_TYPES: frozenset[str] = SAFE_AUTO_ACTION_TYPES | HITL_ACTION_TYPES


def _default_requires_hitl(action_type: str) -> bool:
    return action_type in HITL_ACTION_TYPES


def normalize_corrective_action(raw: dict[str, Any] | CorrectiveAction) -> CorrectiveAction:
    """Validate action_type against allowlist; coerce requires_hitl."""
    if isinstance(raw, CorrectiveAction):
        action = raw
    else:
        try:
            action = CorrectiveAction.model_validate(raw)
        except ValidationError as exc:
            at = (raw.get("action_type") if isinstance(raw, dict) else None) or "?"
            raise ValueError(f"action_type not allowed: {at}") from exc
    if action.action_type not in _ALLOWED_TYPES:
        raise ValueError(f"action_type not allowed: {action.action_type}")
    expected_hitl = _default_requires_hitl(action.action_type)
    if action.action_type != "noop" and action.requires_hitl != expected_hitl:
        action = action.model_copy(update={"requires_hitl": expected_hitl})
    if action.action_type == "noop":
        action = action.model_copy(update={"requires_hitl": False})
    return action


def parse_corrective_actions_json(
    text: str,
    *,
    strict: bool = False,
) -> list[CorrectiveAction]:
    """
    Parse LLM JSON into validated actions.
    On failure returns noop unless strict=True (raises ValueError).
    """
    content = (text or "").strip()
    if not content:
        if strict:
            raise ValueError("empty LLM response")
        return [_noop("empty LLM response")]

    if "```" in content:
        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            content = content[start:end]
        else:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = f"[{content[start:end]}]"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError(f"invalid JSON: {exc}") from exc
        return [_noop(f"invalid JSON: {exc}")]

    if isinstance(data, dict):
        if "actions" in data and isinstance(data["actions"], list):
            items = data["actions"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return [_noop("expected JSON array or object")]

    out: list[CorrectiveAction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(normalize_corrective_action(item))
        except (ValidationError, ValueError) as exc:
            _log.warning("corrective_allowlist: reject item %s: %s", item, exc)
    if not out:
        return [_noop("no valid actions after validation")]
    return out


def _noop(reason: str) -> CorrectiveAction:
    return CorrectiveAction(action_type="noop", requires_hitl=False, reason=reason)
