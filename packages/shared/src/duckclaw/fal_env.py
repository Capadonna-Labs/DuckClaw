"""Resolucion zero-trust de API key Fal.ai (DB-first + env fallback)."""

from __future__ import annotations

from typing import Any


def resolve_fal_api_key(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> str:
    from duckclaw.integration_secrets import resolve_integration_api_key

    return resolve_integration_api_key(
        "fal",
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
        token_env=token_env,
    )


def fal_api_key_configured(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> bool:
    return bool(
        resolve_fal_api_key(
            token_env,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
    )
