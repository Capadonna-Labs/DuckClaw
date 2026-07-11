"""DB-first health checks for prompt policy availability."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from duckclaw.prompt_policies.resolver import normalize_policy_type


FRAMEWORK_PROMPT_POLICY_REQUIREMENTS = (
    ("capability", "generic_worker", "framework"),
    ("capability", "default_fallback", "framework"),
    ("system_prompt", "default", "framework"),
)


INHERITED_SYSTEM_PROMPT_WARNING = "especialización pendiente"


@dataclass(frozen=True)
class PromptPolicyRequirement:
    """A prompt policy the runtime expects to resolve from DuckDB."""

    policy_type: str
    policy_name: str
    source: str = ""

    def normalized(self) -> "PromptPolicyRequirement":
        return PromptPolicyRequirement(
            normalize_policy_type(self.policy_type),
            (self.policy_name or "").strip(),
            (self.source or "").strip(),
        )


@dataclass(frozen=True)
class PromptPolicyHealthClassification:
    """Partition of prompt policy requirements by health severity."""

    missing: tuple[PromptPolicyRequirement, ...]
    inherited: tuple[PromptPolicyRequirement, ...]
    ok: tuple[PromptPolicyRequirement, ...]

    @property
    def is_ok(self) -> bool:
        return not self.missing


def classify_prompt_policy_health(
    db: Any | None,
    requirements: Iterable[PromptPolicyRequirement],
) -> PromptPolicyHealthClassification:
    """Classify requirements into critical missing, inherited warnings, and ok."""

    if db is None:
        raise RuntimeError("prompt policy health requires a DuckDB connection")

    missing: list[PromptPolicyRequirement] = []
    inherited: list[PromptPolicyRequirement] = []
    ok: list[PromptPolicyRequirement] = []
    seen: set[tuple[str, str, str]] = set()
    for requirement in requirements:
        normalized = requirement.normalized()
        _validate_requirement(normalized)
        key = (normalized.policy_type, normalized.policy_name, normalized.source)
        if key in seen:
            continue
        seen.add(key)
        if _active_policy_exists(db, normalized.policy_type, normalized.policy_name):
            ok.append(normalized)
        elif _is_inherited_system_prompt_requirement(db, normalized):
            inherited.append(normalized)
        else:
            missing.append(normalized)
    return PromptPolicyHealthClassification(
        missing=tuple(missing),
        inherited=tuple(inherited),
        ok=tuple(ok),
    )


def missing_prompt_policies(
    db: Any | None,
    requirements: Iterable[PromptPolicyRequirement],
) -> list[PromptPolicyRequirement]:
    """Return requirements that do not have an active DB policy row."""

    if db is None:
        raise RuntimeError("prompt policy health requires a DuckDB connection")

    missing: list[PromptPolicyRequirement] = []
    seen: set[tuple[str, str, str]] = set()
    for requirement in requirements:
        normalized = requirement.normalized()
        _validate_requirement(normalized)
        key = (normalized.policy_type, normalized.policy_name, normalized.source)
        if key in seen:
            continue
        seen.add(key)
        if not _active_policy_exists(db, normalized.policy_type, normalized.policy_name):
            missing.append(normalized)
    return missing


def prompt_policy_requirements_for_workers(
    worker_ids: Iterable[str],
    *,
    include_framework: bool = True,
) -> list[PromptPolicyRequirement]:
    """Build DB policy requirements for framework and worker identities."""

    requirements: list[PromptPolicyRequirement] = []
    if include_framework:
        requirements.extend(
            PromptPolicyRequirement(policy_type, policy_name, source)
            for policy_type, policy_name, source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
        )
    normalized_worker_ids = sorted(
        {
            str(worker_id or "").strip()
            for worker_id in worker_ids
            if str(worker_id or "").strip()
        }
    )
    requirements.extend(
        PromptPolicyRequirement("system_prompt", worker_id, "worker")
        for worker_id in normalized_worker_ids
    )
    return requirements


def _validate_requirement(requirement: PromptPolicyRequirement) -> None:
    if not requirement.policy_type or not requirement.policy_name:
        raise ValueError("prompt policy requirement requires type and name")


def _is_inherited_system_prompt_requirement(
    db: Any,
    requirement: PromptPolicyRequirement,
) -> bool:
    if requirement.policy_type != "system_prompt" or requirement.source != "worker":
        return False
    worker_id = requirement.policy_name
    if not worker_id or worker_id == "default":
        return False
    if not _catalog_worker_exists(db, worker_id):
        return False
    return _active_policy_exists(db, "system_prompt", "default")


def _catalog_worker_exists(db: Any, worker_id: str) -> bool:
    result = db.execute(
        """
        SELECT 1
        FROM main.admin_worker_catalog
        WHERE worker_id = ?
          AND active = true
        LIMIT 1
        """,
        [worker_id],
    )
    if isinstance(result, list):
        return bool(result)
    if hasattr(result, "fetchone"):
        return result.fetchone() is not None
    if hasattr(result, "fetchall"):
        return bool(result.fetchall())
    return bool(result)


def _active_policy_exists(db: Any, policy_type: str, policy_name: str) -> bool:
    result = db.execute(
        """
        SELECT 1
        FROM main.prompt_policy_registry
        WHERE policy_type = ?
          AND policy_name = ?
          AND active = true
          AND status = 'active'
        LIMIT 1
        """,
        [policy_type, policy_name],
    )
    if isinstance(result, list):
        return bool(result)
    if hasattr(result, "fetchone"):
        return result.fetchone() is not None
    if hasattr(result, "fetchall"):
        return bool(result.fetchall())
    return bool(result)
