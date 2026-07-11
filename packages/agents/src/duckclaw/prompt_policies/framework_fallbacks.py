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


def _airbag_policy_keys() -> frozenset[tuple[str, str]]:
    from duckclaw.prompt_policies.health import FRAMEWORK_PROMPT_POLICY_REQUIREMENTS

    return frozenset(
        (policy_type, policy_name)
        for policy_type, policy_name, _source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
    )


def is_framework_policy_key(policy_type: str, policy_name: str) -> bool:
    normalized_type = (policy_type or "").strip().lower()
    name = (policy_name or "").strip()
    return (normalized_type, name) in _airbag_policy_keys()


def framework_fallback_content(policy_type: str, policy_name: str) -> str | None:
    if not is_framework_policy_key(policy_type, policy_name):
        return None
    return get_framework_policy_content(policy_type, policy_name)


def list_framework_fallback_keys() -> frozenset[tuple[str, str]]:
    airbag = _airbag_policy_keys()
    pack_keys = framework_policy_keys()
    missing = airbag - pack_keys
    if missing:
        raise RuntimeError(
            "framework policy pack missing required airbag keys: "
            f"{sorted(missing)}"
        )
    _ = load_framework_policy_pack()
    return airbag
