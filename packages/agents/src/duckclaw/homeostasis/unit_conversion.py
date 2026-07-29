"""Generic observed-value unit normalization for homeostasis goals.

Callers inject ``settings_lookup`` (key → float); core never interprets key names.
Extensions populate session settings; DuckClaw only resolves keys by name.
"""

from __future__ import annotations

from typing import Any, Iterable


def normalize_observed(
    raw_value: float,
    *,
    target_unit: str,
    anchor_setting_key: str | None,
    settings_lookup: dict[str, float],
) -> float:
    """Convert raw observed to the unit declared by the goal target."""
    unit = (target_unit or "raw").strip().lower()
    if unit in ("raw", ""):
        return float(raw_value)
    if unit == "usd":
        return float(raw_value)
    if unit == "pct":
        key = (anchor_setting_key or "").strip()
        if not key:
            raise ValueError("target_unit='pct' requires anchor_setting_key")
        anchor = settings_lookup.get(key)
        if anchor is None or anchor == 0:
            raise ValueError(
                f"anchor_setting_key '{key}' did not resolve to a valid numeric anchor"
            )
        return (float(raw_value) / float(anchor)) * 100.0
    raise ValueError(f"unknown target_unit: {target_unit}")


def build_settings_lookup(
    db: Any,
    chat_id: Any,
    tenant_id: str,
    keys: Iterable[str],
) -> dict[str, float]:
    """Resolve numeric session settings for the given opaque keys."""
    from duckclaw.runtime_session_settings import resolve_session_runtime_setting

    out: dict[str, float] = {}
    seen: set[str] = set()
    tid = str(tenant_id or "default").strip() or "default"
    for raw_key in keys:
        key = (raw_key or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        raw_val = resolve_session_runtime_setting(db, chat_id, key, tenant_id=tid)
        try:
            parsed = float(str(raw_val).strip())
        except (TypeError, ValueError):
            continue
        out[key] = parsed
    return out


def goal_target_unit(goal: dict[str, Any]) -> str:
    return (str(goal.get("target_unit") or "raw")).strip().lower() or "raw"


def collect_anchor_keys(goals: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for g in goals:
        if not isinstance(g, dict):
            continue
        if goal_target_unit(g) != "pct":
            continue
        key = (str(g.get("anchor_setting_key") or "")).strip()
        if key:
            keys.append(key)
    return keys


def needs_pct_conversion(observed: float, target: float, threshold: float) -> bool:
    """True when observed appears to be absolute units but target is percent-scale."""
    from duckclaw.homeostasis.surprise import detect_value_scale_mismatch

    return detect_value_scale_mismatch(
        observed, target, threshold, value_unit="percent"
    )


def try_normalize_goal_observed(
    goal: dict[str, Any],
    *,
    settings_lookup: dict[str, float],
    target: float,
    threshold: float,
) -> float | None:
    """Normalize observed when target_unit requires conversion and scales mismatch."""
    raw = goal.get("observed_value")
    if raw is None:
        return None
    try:
        raw_f = float(raw)
    except (TypeError, ValueError):
        return None
    unit = goal_target_unit(goal)
    if unit == "raw":
        return raw_f
    if unit == "usd":
        return raw_f
    if unit != "pct":
        return raw_f
    if not needs_pct_conversion(raw_f, target, threshold):
        return raw_f
    try:
        return normalize_observed(
            raw_f,
            target_unit="pct",
            anchor_setting_key=str(goal.get("anchor_setting_key") or ""),
            settings_lookup=settings_lookup,
        )
    except ValueError:
        return raw_f
