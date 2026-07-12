"""Shared integration readiness report (sensors, doctor, capabilities)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duckclaw.integration_catalog import (
    IntegrationCatalogEntry,
    _env_fallback_label,
    list_integration_catalog_entries,
)
from duckclaw.integration_secrets import integration_api_key_configured


@dataclass(frozen=True)
class IntegrationReadiness:
    integration_id: str
    label: str
    configured: bool
    env_fallback: str
    related_skills: tuple[str, ...]

    @classmethod
    def from_entry(
        cls,
        entry: IntegrationCatalogEntry,
        *,
        configured: bool,
    ) -> IntegrationReadiness:
        return cls(
            integration_id=entry.integration_id,
            label=entry.label,
            configured=configured,
            env_fallback=_env_fallback_label(entry.env_keys),
            related_skills=entry.related_skills,
        )


def build_integration_readiness(
    db: Any | None = None,
    *,
    tenant_id: str = "default",
    actor_email: str = "",
) -> tuple[IntegrationReadiness, ...]:
    rows: list[IntegrationReadiness] = []
    for entry in list_integration_catalog_entries():
        configured = integration_api_key_configured(
            entry.integration_id,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
        rows.append(IntegrationReadiness.from_entry(entry, configured=configured))
    return tuple(rows)


def missing_integration_labels(
    db: Any | None = None,
    *,
    tenant_id: str = "default",
    actor_email: str = "",
) -> tuple[str, ...]:
    return tuple(row.label for row in build_integration_readiness(db, tenant_id=tenant_id, actor_email=actor_email) if not row.configured)


def integration_catalog_sensor_lines(
    db: Any | None = None,
    *,
    tenant_id: str = "default",
    actor_email: str = "",
) -> list[str]:
    """Compact /sensors block for bundled integration API keys."""
    rows = build_integration_readiness(db, tenant_id=tenant_id, actor_email=actor_email)
    if not rows:
        return []
    lines = ["🔑 Integraciones (API keys)"]
    for row in rows:
        if row.configured:
            lines.append(f"   ✅ {row.label}")
        else:
            fallback = row.env_fallback if row.env_fallback != "—" else "sin env fallback"
            lines.append(f"   ⚠️ {row.label} · Admin → Integraciones o {fallback}")
    return lines
