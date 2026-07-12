"""Integration secret gaps derived from catalog + effective worker skills."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from duckclaw.integration_catalog import (
    IntegrationCatalogEntry,
    _env_fallback_label,
    list_integration_catalog_entries,
)


def _normalize_skill_id(value: str) -> str:
    return (value or "").strip().lower().replace("-", "_")


@lru_cache(maxsize=1)
def _integrations_by_skill() -> dict[str, tuple[IntegrationCatalogEntry, ...]]:
    index: dict[str, list[IntegrationCatalogEntry]] = {}
    for entry in list_integration_catalog_entries():
        for skill in entry.related_skills:
            key = _normalize_skill_id(skill)
            if not key:
                continue
            index.setdefault(key, []).append(entry)
    return {key: tuple(items) for key, items in index.items()}


def integrations_for_skill(skill_id: str) -> tuple[IntegrationCatalogEntry, ...]:
    return _integrations_by_skill().get(_normalize_skill_id(skill_id), ())


def clear_integration_gaps_cache() -> None:
    _integrations_by_skill.cache_clear()


def build_integration_secret_gaps(
    skills_effective: list[str],
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> list[dict[str, Any]]:
    """Structured gaps for skills that need an integration API key."""
    from duckclaw.integration_secrets import integration_api_key_configured

    active = {_normalize_skill_id(skill) for skill in skills_effective if _normalize_skill_id(skill)}
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()

    for skill in sorted(active):
        for entry in integrations_for_skill(skill):
            dedupe = f"{skill}:{entry.integration_id}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            configured = integration_api_key_configured(
                entry.integration_id,
                db=db,
                tenant_id=tenant_id,
                actor_email=actor_email,
            )
            if configured:
                continue
            env_fallback = _env_fallback_label(entry.env_keys)
            gaps.append(
                {
                    "skill": skill,
                    "integration_id": entry.integration_id,
                    "label": entry.label,
                    "setting_key": entry.setting_key,
                    "env_fallback": env_fallback,
                    "configured": False,
                    "admin_href": "/integraciones?tab=keys",
                    "message": (
                        f"skill {skill} efectiva pero falta API key {entry.label} "
                        f"(Admin → Integraciones → API keys"
                        + (f", o {env_fallback} en .env bootstrap)" if env_fallback != "—" else ")")
                    ),
                }
            )
    return gaps


def build_optional_integration_flags(
    skills_effective: list[str],
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> dict[str, bool]:
    """True when skill is active and its integration secret is configured."""
    from duckclaw.integration_secrets import integration_api_key_configured

    active = {_normalize_skill_id(skill) for skill in skills_effective if _normalize_skill_id(skill)}
    flags: dict[str, bool] = {}
    for skill in active:
        for entry in integrations_for_skill(skill):
            flags[entry.integration_id] = integration_api_key_configured(
                entry.integration_id,
                db=db,
                tenant_id=tenant_id,
                actor_email=actor_email,
            )
    return flags


def integration_gap_messages(gaps: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("message") or "").strip() for item in gaps if str(item.get("message") or "").strip()]
