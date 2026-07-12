"""Resolucion zero-trust de API key Higgsfield (DB-first + env fallback)."""

from __future__ import annotations

from typing import Any

_HIGGSFIELD_KEY_CANDIDATES = ("HIGGSFIELD_API_KEY", "HIGGSFIELD_KEY")


def resolve_higgsfield_api_key(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> str:
    from duckclaw.integration_secrets import resolve_integration_api_key

    return resolve_integration_api_key(
        "higgsfield",
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
        token_env=token_env,
    )


def higgsfield_api_key_configured(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> bool:
    return bool(
        resolve_higgsfield_api_key(
            token_env,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
    )
