"""Framework prompt policy preflight for duckops doctor and TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duckclaw.prompt_policies.framework_fallbacks import framework_fallback_content
from duckclaw.prompt_policies.health import (
    FRAMEWORK_PROMPT_POLICY_REQUIREMENTS,
    PromptPolicyRequirement,
    missing_prompt_policies,
)


@dataclass(frozen=True)
class FrameworkPolicyHealth:
    ok: bool
    degraded_keys: tuple[str, ...]
    missing_keys: tuple[str, ...]

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_keys)

    def summary(self) -> str:
        if self.ok and not self.degraded:
            return "framework policies activas en DuckDB"
        if self.ok and self.degraded:
            return (
                f"degradado capa 0 ({len(self.degraded_keys)} sin fila DB): "
                + ", ".join(self.degraded_keys)
            )
        return f"faltan policies críticas: {', '.join(self.missing_keys)}"


def check_framework_prompt_policies(db: Any) -> FrameworkPolicyHealth:
    """Return health for the 4 framework keys required at runtime."""

    requirements = [
        PromptPolicyRequirement(policy_type, policy_name, source)
        for policy_type, policy_name, source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
    ]
    missing_db = missing_prompt_policies(db, requirements)
    degraded: list[str] = []
    critical: list[str] = []
    for item in missing_db:
        key = f"{item.policy_type}/{item.policy_name}"
        if framework_fallback_content(item.policy_type, item.policy_name):
            degraded.append(key)
        else:
            critical.append(key)
    return FrameworkPolicyHealth(
        ok=not critical,
        degraded_keys=tuple(degraded),
        missing_keys=tuple(critical),
    )
