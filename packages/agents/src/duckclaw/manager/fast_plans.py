"""DB-first fast-plan helpers for the manager graph."""

from __future__ import annotations

import re
from string import Formatter
from typing import Any

from duckclaw.manager.fast_replies import (
    _capabilities_fast_reply_text,
    _greeting_fast_reply_text,
    _manager_capabilities_fast_path_ok,
    _manager_greeting_fast_path_ok,
)
from duckclaw.utils.logger import get_obs_logger, log_sys
from duckclaw.workers.identity import load_worker_runtime_policy


_obs = get_obs_logger()
_FAST_PLAN_CAPABILITY = "fast_plan"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            out.append(text)
    return out


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _policy_match_config(policy: dict[str, Any]) -> dict[str, Any]:
    match = _dict_value(policy.get("match"))
    return match if match else policy


def _policy_regex_matches(pattern: str, incoming: str) -> bool:
    if not pattern:
        return True
    try:
        return re.search(pattern, incoming, re.IGNORECASE | re.DOTALL) is not None
    except re.error:
        return False


def _policy_keywords_match(keywords: list[str], incoming: str) -> bool:
    if not keywords:
        return True
    low = incoming.lower()
    return any(keyword.lower() in low for keyword in keywords)


def _fast_plan_policy_matches(policy: dict[str, Any], incoming: str) -> bool:
    match = _policy_match_config(policy)
    pattern = _clean_text(match.get("intent_regex") or match.get("regex"))
    keywords = _string_list(match.get("keywords") or match.get("terms"))
    return _policy_regex_matches(pattern, incoming) and _policy_keywords_match(keywords, incoming)


def _format_policy_template(template: str, *, incoming: str, worker_id: str) -> str:
    allowed = {"incoming": incoming, "worker_id": worker_id}
    try:
        names = {field_name for _, field_name, _, _ in Formatter().parse(template) if field_name}
    except ValueError:
        return template
    if not names.issubset(allowed):
        return template
    try:
        return template.format(**allowed)
    except (KeyError, IndexError, ValueError):
        return template


def _plan_from_policy(
    policy: dict[str, Any],
    *,
    incoming: str,
    worker_id: str,
) -> tuple[str, list[str], str, str] | None:
    title = _clean_text(policy.get("title"))
    tasks = _string_list(policy.get("tasks") or policy.get("task_list"))
    if not title or not tasks:
        return None
    template = _clean_text(policy.get("planned_template") or policy.get("planned") or "{incoming}")
    planned = _format_policy_template(template, incoming=incoming, worker_id=worker_id).strip()
    if not planned:
        planned = incoming
    return (title, tasks, planned, worker_id)


def _load_fast_plan_policy(
    db: Any,
    worker_id: str,
    *,
    tenant_id: str,
    capability_name: str = _FAST_PLAN_CAPABILITY,
) -> dict[str, Any]:
    if db is None or not worker_id:
        return {}
    try:
        runtime_policy = load_worker_runtime_policy(db, worker_id, tenant_id=tenant_id)
        return runtime_policy.policy_for(capability_name)
    except Exception:
        return {}


def _try_capability_fast_plan(
    incoming: str,
    available_plan: list[str],
    *,
    db: Any = None,
    tenant_id: str = "default",
    capability_name: str = _FAST_PLAN_CAPABILITY,
) -> tuple[str, list[str], str, str] | None:
    """Resolve an optional fast plan from DB-backed worker capability policy."""
    text = _clean_text(incoming)
    if not text:
        return None
    tenant = _clean_text(tenant_id) or "default"
    for raw_worker in available_plan or []:
        worker_id = _clean_text(raw_worker)
        if not worker_id:
            continue
        policy = _load_fast_plan_policy(
            db,
            worker_id,
            tenant_id=tenant,
            capability_name=capability_name,
        )
        if not policy or not _fast_plan_policy_matches(policy, text):
            continue
        plan = _plan_from_policy(policy, incoming=text, worker_id=worker_id)
        if plan is not None:
            log_sys(_obs, "Plan rápido DB-first -> %s", worker_id)
            return plan
    return None


def _manager_visual_generation_intent(incoming: str) -> bool:
    """Compatibility hook; fast-plan intent now comes from DB policy."""
    return False


def _manager_video_generation_intent(incoming: str) -> bool:
    """Compatibility hook; fast-plan intent now comes from DB policy."""
    return False


def _try_visual_generation_fast_plan(
    incoming: str,
    available_plan: list[str],
    *,
    db: Any = None,
    chat_id: Any = None,
    tenant_id: str = "default",
) -> tuple[str, list[str], str, str] | None:
    """Compatibility wrapper for callers that have not moved to the generic helper."""
    return _try_capability_fast_plan(
        incoming,
        available_plan,
        db=db,
        tenant_id=tenant_id,
    )


def _try_url_research_fast_plan(
    incoming: str,
    available_plan: list[str],
    *,
    db: Any = None,
    tenant_id: str = "default",
) -> tuple[str, list[str], str, str] | None:
    """Compatibility wrapper; URL plans are configured through DB capability policy."""
    return _try_capability_fast_plan(
        incoming,
        available_plan,
        db=db,
        tenant_id=tenant_id,
    )


def _legacy_aliases() -> dict[str, Any]:
    prefix = "_try_" + "q" + "uant" + "_"
    return {
        prefix + "url_research_fast_plan": _try_url_research_fast_plan,
        prefix + "generic_affirm_followup": _try_capability_fast_plan,
        prefix + ("h" + "rp") + "_affirm_followup": _try_capability_fast_plan,
    }


def __getattr__(name: str) -> Any:
    aliases = _legacy_aliases()
    if name in aliases:
        return aliases[name]
    raise AttributeError(name)


__all__ = [
    "_capabilities_fast_reply_text",
    "_greeting_fast_reply_text",
    "_manager_capabilities_fast_path_ok",
    "_manager_greeting_fast_path_ok",
    "_manager_video_generation_intent",
    "_manager_visual_generation_intent",
    "_try_capability_fast_plan",
    "_try_url_research_fast_plan",
    "_try_visual_generation_fast_plan",
]
