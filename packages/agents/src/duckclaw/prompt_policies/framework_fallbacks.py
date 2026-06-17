"""Capa 0 airbag — framework prompt policies when DuckDB rows are missing."""

from __future__ import annotations

from duckclaw.framework_policy_pack import (
    PACK_SEED,
    framework_policy_keys,
    get_framework_policy_content,
    load_framework_policy_pack,
)

__all__ = [
    "FRAMEWORK_FALLBACK_SEED",
    "framework_fallback_content",
    "is_framework_policy_key",
    "list_framework_fallback_keys",
]


FRAMEWORK_FALLBACK_SEED = PACK_SEED


def is_framework_policy_key(policy_type: str, policy_name: str) -> bool:
    normalized_type = (policy_type or "").strip().lower()
    name = (policy_name or "").strip()
    return (normalized_type, name) in framework_policy_keys()


def framework_fallback_content(policy_type: str, policy_name: str) -> str | None:
    if not is_framework_policy_key(policy_type, policy_name):
        return None
    return get_framework_policy_content(policy_type, policy_name)


def list_framework_fallback_keys() -> frozenset[tuple[str, str]]:
    from duckclaw.prompt_policies.health import FRAMEWORK_PROMPT_POLICY_REQUIREMENTS

    pack_keys = framework_policy_keys()
    required = {
        (policy_type, policy_name)
        for policy_type, policy_name, _source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
    }
    if pack_keys != required:
        missing = required - pack_keys
        extra = pack_keys - required
        raise RuntimeError(
            "framework policy pack keys drift from FRAMEWORK_PROMPT_POLICY_REQUIREMENTS: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    _ = load_framework_policy_pack()
    return pack_keys
